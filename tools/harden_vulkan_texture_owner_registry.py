from __future__ import annotations

import argparse
from pathlib import Path


REGISTRY_BLOCK = r'''    struct xr_vk_texture_owner_entry
    {
        const CTexture* owner;
        xr_vk_texture_resource* resource;

        xr_vk_texture_owner_entry() : owner(NULL), resource(NULL) {}
    };

    enum { XR_VK_TEXTURE_OWNER_CAPACITY = 8192 };
    xr_vk_texture_owner_entry g_texture_owner_registry[XR_VK_TEXTURE_OWNER_CAPACITY];

    bool xr_vk_texture_resource_alive(const xr_vk_texture_resource* resource)
    {
        return resource && resource->image != VK_NULL_HANDLE && resource->view != VK_NULL_HANDLE;
    }

    bool xr_vk_texture_resource_shader_readable(const xr_vk_texture_resource* resource)
    {
        return xr_vk_texture_resource_alive(resource) &&
            (resource->layout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL ||
             resource->layout == VK_IMAGE_LAYOUT_GENERAL);
    }

    bool xr_vk_register_texture_owner(const CTexture* owner, xr_vk_texture_resource& resource)
    {
        if (!owner || !xr_vk_texture_resource_alive(&resource))
            return false;

        for (u32 index = 0; index < XR_VK_TEXTURE_OWNER_CAPACITY; ++index)
        {
            xr_vk_texture_owner_entry& entry = g_texture_owner_registry[index];
            if (entry.owner == owner)
            {
                entry.resource = &resource;
                return true;
            }
        }

        for (u32 index = 0; index < XR_VK_TEXTURE_OWNER_CAPACITY; ++index)
        {
            xr_vk_texture_owner_entry& entry = g_texture_owner_registry[index];
            if (!entry.owner)
            {
                entry.owner = owner;
                entry.resource = &resource;
                return true;
            }
        }

        return false;
    }

    void xr_vk_unregister_texture_owner(const CTexture* owner)
    {
        if (!owner)
            return;
        for (u32 index = 0; index < XR_VK_TEXTURE_OWNER_CAPACITY; ++index)
        {
            xr_vk_texture_owner_entry& entry = g_texture_owner_registry[index];
            if (entry.owner == owner)
            {
                entry.owner = NULL;
                entry.resource = NULL;
                return;
            }
        }
    }

    void xr_vk_unregister_texture_resource(const xr_vk_texture_resource* resource)
    {
        if (!resource)
            return;
        for (u32 index = 0; index < XR_VK_TEXTURE_OWNER_CAPACITY; ++index)
        {
            xr_vk_texture_owner_entry& entry = g_texture_owner_registry[index];
            if (entry.resource == resource)
            {
                entry.owner = NULL;
                entry.resource = NULL;
            }
        }
    }

    const xr_vk_texture_resource* xr_vk_find_texture_resource(const CTexture* owner)
    {
        if (!owner)
            return NULL;
        for (u32 index = 0; index < XR_VK_TEXTURE_OWNER_CAPACITY; ++index)
        {
            const xr_vk_texture_owner_entry& entry = g_texture_owner_registry[index];
            if (entry.owner == owner)
                return xr_vk_texture_resource_shader_readable(entry.resource) ? entry.resource : NULL;
        }
        return NULL;
    }

    bool xr_vk_texture_snapshot_resolved(CTexture* const* textures, u32 texture_count)
    {
        if (!textures)
            return false;
        for (u32 index = 0; index < texture_count; ++index)
        {
            if (textures[index] && !xr_vk_find_texture_resource(textures[index]))
                return false;
        }
        return true;
    }

'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "struct xr_vk_texture_resource" not in text or "xr_vk_create_texture_2d" not in text:
        raise RuntimeError("Vulkan texture owner registry requires the sampled-image texture bridge")

    marker = "    u32 xr_vk_max_mip_levels(u32 width, u32 height)\n"
    if "XR_VK_TEXTURE_OWNER_CAPACITY" not in text:
        if marker not in text:
            raise RuntimeError("Vulkan texture owner registry: texture helper marker missing")
        text = text.replace(marker, REGISTRY_BLOCK + marker, 1)

    destroy_old = '''    void xr_vk_destroy_texture(xr_vk_texture_resource& texture)
    {
        if (g_device != VK_NULL_HANDLE && texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
'''
    destroy_new = '''    void xr_vk_destroy_texture(xr_vk_texture_resource& texture)
    {
        xr_vk_unregister_texture_resource(&texture);
        if (g_device != VK_NULL_HANDLE && texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
'''
    if "xr_vk_unregister_texture_resource(&texture);" not in text:
        if destroy_old not in text:
            raise RuntimeError("Vulkan texture owner registry: texture destruction marker missing")
        text = text.replace(destroy_old, destroy_new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_texture_owner_entry",
        "XR_VK_TEXTURE_OWNER_CAPACITY = 8192",
        "xr_vk_texture_resource_alive",
        "xr_vk_texture_resource_shader_readable",
        "VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL",
        "VK_IMAGE_LAYOUT_GENERAL",
        "xr_vk_register_texture_owner",
        "xr_vk_unregister_texture_owner",
        "xr_vk_unregister_texture_resource",
        "xr_vk_find_texture_resource",
        "xr_vk_texture_snapshot_resolved",
        "if (textures[index] && !xr_vk_find_texture_resource(textures[index]))",
        "xr_vk_unregister_texture_resource(&texture);",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan texture owner registry validation failed: missing {token}")

    if final.count("struct xr_vk_texture_owner_entry") != 1:
        raise RuntimeError("Vulkan texture owner registry validation failed: duplicate registry materialization")

    print("[vulkan-texture-owners] bounded CTexture* -> shader-readable Vulkan sampled-image registry + stale-resource cleanup installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge legacy X-Ray CTexture ownership identity to Vulkan sampled-image resources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
