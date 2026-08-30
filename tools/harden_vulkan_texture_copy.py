from __future__ import annotations

import argparse
from pathlib import Path


BLOCK_HELPER = r'''    bool xr_vk_texture_block_info(VkFormat format, u32& block_width, u32& block_height, u32& block_bytes)
    {
        block_width = 1;
        block_height = 1;
        switch (format)
        {
        case VK_FORMAT_R8_UNORM:
            block_bytes = 1;
            return true;
        case VK_FORMAT_R8G8_UNORM:
        case VK_FORMAT_R5G6B5_UNORM_PACK16:
        case VK_FORMAT_A1R5G5B5_UNORM_PACK16:
        case VK_FORMAT_B4G4R4A4_UNORM_PACK16:
            block_bytes = 2;
            return true;
        case VK_FORMAT_B8G8R8A8_UNORM:
        case VK_FORMAT_R8G8B8A8_UNORM:
            block_bytes = 4;
            return true;
        case VK_FORMAT_BC1_RGBA_UNORM_BLOCK:
            block_width = 4;
            block_height = 4;
            block_bytes = 8;
            return true;
        case VK_FORMAT_BC2_UNORM_BLOCK:
        case VK_FORMAT_BC3_UNORM_BLOCK:
            block_width = 4;
            block_height = 4;
            block_bytes = 16;
            return true;
        default:
            block_bytes = 0;
            return false;
        }
    }

'''

COPY_GUARD_OLD = r'''        u32 mip_width = 0;
        u32 mip_height = 0;
        xr_vk_mip_extent(texture, mip_level, mip_width, mip_height);
        if (width > mip_width || height > mip_height)
            return false;

        VkBufferImageCopy copy = {};
'''

COPY_GUARD_NEW = r'''        u32 mip_width = 0;
        u32 mip_height = 0;
        xr_vk_mip_extent(texture, mip_level, mip_width, mip_height);
        if (width > mip_width || height > mip_height)
            return false;

        u32 block_width = 0;
        u32 block_height = 0;
        u32 block_bytes = 0;
        if (!xr_vk_texture_block_info(texture.format, block_width, block_height, block_bytes) || !block_bytes)
            return false;
        if ((staging_offset % block_bytes) != 0)
            return false;
        if (width != mip_width && (width % block_width) != 0)
            return false;
        if (height != mip_height && (height % block_height) != 0)
            return false;

        VkBufferImageCopy copy = {};
'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    if "bool xr_vk_texture_block_info(" not in text:
        marker = "    VkFormat xr_vk_d3d_texture_format(D3DFORMAT format)\n"
        if marker not in text:
            raise RuntimeError("Vulkan texture copy hardening: texture format marker not found")
        text = text.replace(marker, BLOCK_HELPER + marker, 1)

    if "staging_offset % block_bytes" not in text:
        if COPY_GUARD_OLD not in text:
            raise RuntimeError("Vulkan texture copy hardening: mip copy guard marker not found")
        text = text.replace(COPY_GUARD_OLD, COPY_GUARD_NEW, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "bool xr_vk_texture_block_info(VkFormat format",
        "VK_FORMAT_BC1_RGBA_UNORM_BLOCK",
        "block_width = 4",
        "block_height = 4",
        "block_bytes = 8",
        "block_bytes = 16",
        "staging_offset % block_bytes",
        "width != mip_width && (width % block_width) != 0",
        "height != mip_height && (height % block_height) != 0",
    )
    missing = [token for token in required if token not in final]
    if missing:
        raise RuntimeError("Vulkan texture copy hardening failed; missing: " + ", ".join(missing))

    print("[vulkan-texture-copy] texel-block offset/alignment + BC1/2/3 partial-copy rules installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Vulkan texture uploads for texel-block alignment and BC formats.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
