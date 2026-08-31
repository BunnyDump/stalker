from __future__ import annotations

import argparse
from pathlib import Path


SNAPSHOT_BLOCK = r'''    enum
    {
        XR_VK_PIXEL_TEXTURE_SLOTS = 16,
        XR_VK_VERTEX_TEXTURE_SLOTS = 5,
    };

    struct xr_vk_resolved_texture_snapshot
    {
        const xr_vk_texture_resource* pixel[XR_VK_PIXEL_TEXTURE_SLOTS];
        const xr_vk_texture_resource* vertex[XR_VK_VERTEX_TEXTURE_SLOTS];

        xr_vk_resolved_texture_snapshot()
        {
            ZeroMemory(pixel, sizeof(pixel));
            ZeroMemory(vertex, sizeof(vertex));
        }
    };

    bool xr_vk_resolve_texture_stage(CTexture* const* textures, u32 texture_count,
        const u32 expected_count, const xr_vk_texture_resource** resolved)
    {
        if (!textures || !resolved || texture_count != expected_count)
            return false;

        for (u32 index = 0; index < expected_count; ++index)
        {
            resolved[index] = NULL;
            if (!textures[index])
                continue;

            const xr_vk_texture_resource* resource = xr_vk_find_texture_resource(textures[index]);
            if (!resource)
                return false;
            resolved[index] = resource;
        }
        return true;
    }

    bool xr_vk_resolve_texture_snapshot(CTexture* const* pixel_textures, u32 pixel_texture_count,
        CTexture* const* vertex_textures, u32 vertex_texture_count, xr_vk_resolved_texture_snapshot& snapshot)
    {
        snapshot = xr_vk_resolved_texture_snapshot();
        return xr_vk_resolve_texture_stage(pixel_textures, pixel_texture_count,
                   XR_VK_PIXEL_TEXTURE_SLOTS, snapshot.pixel) &&
            xr_vk_resolve_texture_stage(vertex_textures, vertex_texture_count,
                   XR_VK_VERTEX_TEXTURE_SLOTS, snapshot.vertex);
    }

'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "xr_vk_find_texture_resource" not in text or "XR_VK_TEXTURE_OWNER_CAPACITY" not in text:
        raise RuntimeError("Vulkan texture snapshot resolution requires the CTexture owner registry")

    marker = "    bool xr_vk_texture_snapshot_resolved(CTexture* const* textures, u32 texture_count)\n"
    if "struct xr_vk_resolved_texture_snapshot" not in text:
        if marker not in text:
            raise RuntimeError("Vulkan texture snapshot resolution: owner-registry marker missing")
        text = text.replace(marker, SNAPSHOT_BLOCK + marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "XR_VK_PIXEL_TEXTURE_SLOTS = 16",
        "XR_VK_VERTEX_TEXTURE_SLOTS = 5",
        "struct xr_vk_resolved_texture_snapshot",
        "const xr_vk_texture_resource* pixel[XR_VK_PIXEL_TEXTURE_SLOTS]",
        "const xr_vk_texture_resource* vertex[XR_VK_VERTEX_TEXTURE_SLOTS]",
        "bool xr_vk_resolve_texture_stage",
        "texture_count != expected_count",
        "const xr_vk_texture_resource* resource = xr_vk_find_texture_resource(textures[index])",
        "bool xr_vk_resolve_texture_snapshot",
        "XR_VK_PIXEL_TEXTURE_SLOTS, snapshot.pixel",
        "XR_VK_VERTEX_TEXTURE_SLOTS, snapshot.vertex",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan texture snapshot resolution validation failed: missing {token}")

    if final.count("struct xr_vk_resolved_texture_snapshot") != 1:
        raise RuntimeError("Vulkan texture snapshot resolution validation failed: duplicate materialization")

    print("[vulkan-texture-snapshot] exact 16 PS + 5 VS CTexture snapshot resolver installed; null slots preserved and unresolved live textures fail closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve SHOC's exact 16 PS + 5 VS CTexture snapshot into shader-readable Vulkan resources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
