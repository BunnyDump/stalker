from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    required = (
        "PFN_vkCmdCopyBufferToImage g_vkCmdCopyBufferToImage",
        "XR_VK_LOAD_DEVICE(vkCmdCopyBufferToImage)",
        "struct xr_vk_texture_resource",
        "VkFormat xr_vk_d3d_texture_format",
        "D3DFMT_A8R8G8B8", "VK_FORMAT_B8G8R8A8_UNORM",
        "D3DFMT_A8B8G8R8", "VK_FORMAT_R8G8B8A8_UNORM",
        "D3DFMT_DXT1", "VK_FORMAT_BC1_RGBA_UNORM_BLOCK",
        "D3DFMT_DXT3", "VK_FORMAT_BC2_UNORM_BLOCK",
        "D3DFMT_DXT5", "VK_FORMAT_BC3_UNORM_BLOCK",
        "VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT",
        "bool xr_vk_create_texture_2d",
        "VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT",
        "VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT",
        "bool xr_vk_transition_texture",
        "VK_ACCESS_TRANSFER_WRITE_BIT",
        "VK_ACCESS_SHADER_READ_BIT",
        "VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT",
        "bool xr_vk_copy_buffer_to_texture",
        "g_vkCmdCopyBufferToImage(command_buffer, staging_buffer, texture.image",
        "bool xr_vk_allocate_texture_material",
        "texture.layout != VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL",
        "xr_vk_allocate_material_descriptor",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan texture bridge validation failed: missing {token}")

    transition_pos = text.find("bool xr_vk_transition_texture")
    copy_pos = text.find("bool xr_vk_copy_buffer_to_texture")
    material_pos = text.find("bool xr_vk_allocate_texture_material")
    if min(transition_pos, copy_pos, material_pos) < 0 or not transition_pos < copy_pos < material_pos:
        raise RuntimeError("Vulkan texture bridge validation failed: helper ordering is inconsistent")

    unsafe = (
        "D3DFMT_DXT1: return VK_FORMAT_R8G8B8A8_UNORM",
        "texture.layout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;\n        g_vkCmdCopyBufferToImage",
    )
    for token in unsafe:
        if token in text:
            raise RuntimeError(f"Vulkan texture bridge validation failed: unsafe token present: {token}")

    print("[vulkan-textures] materialized texture format/upload/descriptor bridge verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the materialized Vulkan texture bridge.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
