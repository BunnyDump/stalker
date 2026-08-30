from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan texture lifetime hardening requires materialized texture bridge")

    text = source.read_text(encoding="utf-8")

    # destroy_frame_resources() is generated before the texture helper definitions.
    declaration_marker = "    PFN_vkDeviceWaitIdle g_vkDeviceWaitIdle = NULL;\n"
    if "    void xr_vk_collect_deferred_textures();\n" not in text:
        if declaration_marker not in text:
            raise RuntimeError("Vulkan texture lifetime: device-wait marker not found")
        text = text.replace(
            declaration_marker,
            declaration_marker + "    void xr_vk_collect_deferred_textures();\n",
            1,
        )

    old_destroy = r'''    void xr_vk_destroy_texture(xr_vk_texture_resource& texture)
    {
        if (g_device != VK_NULL_HANDLE && texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
            g_vkDestroyImageView(g_device, texture.view, NULL);
        if (g_device != VK_NULL_HANDLE && texture.image != VK_NULL_HANDLE && g_vkDestroyImage)
            g_vkDestroyImage(g_device, texture.image, NULL);
        if (g_device != VK_NULL_HANDLE && texture.memory != VK_NULL_HANDLE && g_vkFreeMemory)
            g_vkFreeMemory(g_device, texture.memory, NULL);
        texture = xr_vk_texture_resource();
    }
'''
    new_destroy = r'''    xr_vector<xr_vk_texture_resource>& xr_vk_deferred_texture_queue()
    {
        static xr_vector<xr_vk_texture_resource> queue;
        return queue;
    }

    void xr_vk_destroy_texture_now(xr_vk_texture_resource& texture)
    {
        if (g_device != VK_NULL_HANDLE && texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
            g_vkDestroyImageView(g_device, texture.view, NULL);
        if (g_device != VK_NULL_HANDLE && texture.image != VK_NULL_HANDLE && g_vkDestroyImage)
            g_vkDestroyImage(g_device, texture.image, NULL);
        if (g_device != VK_NULL_HANDLE && texture.memory != VK_NULL_HANDLE && g_vkFreeMemory)
            g_vkFreeMemory(g_device, texture.memory, NULL);
        texture = xr_vk_texture_resource();
    }

    void xr_vk_collect_deferred_textures()
    {
        xr_vector<xr_vk_texture_resource>& queue = xr_vk_deferred_texture_queue();
        for (u32 i = 0; i < queue.size(); ++i)
            xr_vk_destroy_texture_now(queue[i]);
        queue.clear();
    }

    void xr_vk_destroy_texture(xr_vk_texture_resource& texture)
    {
        if (texture.image == VK_NULL_HANDLE && texture.view == VK_NULL_HANDLE && texture.memory == VK_NULL_HANDLE)
        {
            texture = xr_vk_texture_resource();
            return;
        }

        // With a live frame fence, keep the Vulkan handles alive until the next
        // successful fence wait. This also protects resources referenced by a
        // command buffer that has been recorded but not yet submitted.
        if (g_device != VK_NULL_HANDLE && g_frame_fence != VK_NULL_HANDLE)
        {
            xr_vk_deferred_texture_queue().push_back(texture);
            texture = xr_vk_texture_resource();
            return;
        }

        xr_vk_destroy_texture_now(texture);
    }

    void xr_vk_release_texture_material(xr_vk_texture_resource& texture, VkDescriptorSet& descriptor_set)
    {
        // Descriptor sets must not retain a view that the release path is about to retire.
        xr_vk_free_material_descriptor(descriptor_set);
        xr_vk_destroy_texture(texture);
    }
'''
    if "xr_vk_deferred_texture_queue" not in text:
        if old_destroy not in text:
            raise RuntimeError("Vulkan texture lifetime: original destroy helper not found")
        text = text.replace(old_destroy, new_destroy, 1)

    wait_marker = '''    if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
        return false;

'''
    wait_replacement = wait_marker + '''    // The single in-flight frame is complete; deferred texture handles are now GPU-safe to release.
    xr_vk_collect_deferred_textures();

'''
    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    if frame_start < 0:
        raise RuntimeError("Vulkan texture lifetime: frame function not found")
    if "xr_vk_collect_deferred_textures();" not in text[frame_start:]:
        frame_text = text[frame_start:]
        if wait_marker not in frame_text:
            raise RuntimeError("Vulkan texture lifetime: frame fence wait marker not found")
        frame_text = frame_text.replace(wait_marker, wait_replacement, 1)
        text = text[:frame_start] + frame_text

    idle_marker = '''        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);

'''
    idle_replacement = idle_marker + '''        // Device idle guarantees every queued texture is no longer referenced by the GPU.
        xr_vk_collect_deferred_textures();

'''
    destroy_start = text.find("void xr_vk_destroy_frame_resources()")
    if destroy_start < 0:
        raise RuntimeError("Vulkan texture lifetime: frame-resource destroy function not found")
    destroy_end = text.find("void xr_vk_destroy_window_runtime()", destroy_start)
    destroy_block = text[destroy_start:destroy_end]
    if "xr_vk_collect_deferred_textures();" not in destroy_block:
        if idle_marker not in destroy_block:
            raise RuntimeError("Vulkan texture lifetime: device-idle cleanup marker not found")
        destroy_block = destroy_block.replace(idle_marker, idle_replacement, 1)
        text = text[:destroy_start] + destroy_block + text[destroy_end:]

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_deferred_texture_queue",
        "xr_vk_destroy_texture_now",
        "xr_vk_collect_deferred_textures",
        "xr_vk_release_texture_material",
        "xr_vk_free_material_descriptor(descriptor_set)",
        "xr_vk_deferred_texture_queue().push_back(texture)",
        "The single in-flight frame is complete",
        "Device idle guarantees every queued texture",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan texture lifetime validation failed: missing {token}")

    print("[vulkan-texture-lifetime] descriptor-safe deferred texture destruction installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Defer Vulkan texture destruction until submitted GPU work is complete.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
