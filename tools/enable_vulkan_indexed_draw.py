from __future__ import annotations

import argparse
from pathlib import Path


def install_indexed_draw(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan indexed draw layer requires materialized stream mirror")

    text = source.read_text(encoding="utf-8")
    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    struct xr_vk_indexed_draw_packet
    {
        VkPipeline pipeline;
        VkDeviceSize vertex_offset;
        VkDeviceSize index_offset;
        VkIndexType index_type;
        u32 first_index;
        u32 index_count;
        s32 vertex_offset_bias;
    };

    bool xr_vk_record_indexed_draw(VkCommandBuffer command_buffer, const xr_vk_indexed_draw_packet& draw)
    {
        if (command_buffer == VK_NULL_HANDLE || draw.pipeline == VK_NULL_HANDLE || !draw.index_count ||
            !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed)
            return false;
        if (draw.index_type != VK_INDEX_TYPE_UINT16 && draw.index_type != VK_INDEX_TYPE_UINT32)
            return false;
        if (!xr_vk_bind_stream_geometry(command_buffer, draw.vertex_offset, draw.index_offset, draw.index_type))
            return false;

        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, draw.pipeline);
        g_vkCmdDrawIndexed(command_buffer, draw.index_count, 1, draw.first_index, draw.vertex_offset_bias, 0);
        return true;
    }

    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, D3DFORMAT index_format,
        u32 start_index, u32 primitive_count, s32 base_vertex, VkDeviceSize vertex_offset,
        VkDeviceSize index_stream_offset, xr_vk_indexed_draw_packet& draw)
    {
        VkIndexType index_type = VK_INDEX_TYPE_MAX_ENUM;
        u32 index_stride = 0;
        u32 index_count = 0;
        if (pipeline == VK_NULL_HANDLE ||
            !xr_vk_d3d_index_format_to_type(index_format, index_type, index_stride) ||
            !xr_vk_primitive_element_count(D3DPT_TRIANGLELIST, primitive_count, index_count) ||
            !index_count)
            return false;

        const VkDeviceSize first_index_bytes = static_cast<VkDeviceSize>(start_index) * index_stride;
        const VkDeviceSize absolute_index_offset = index_stream_offset + first_index_bytes;
        if (absolute_index_offset < index_stream_offset)
            return false;

        draw.pipeline = pipeline;
        draw.vertex_offset = vertex_offset;
        draw.index_offset = absolute_index_offset;
        draw.index_type = index_type;
        draw.first_index = 0;
        draw.index_count = index_count;
        draw.vertex_offset_bias = base_vertex;
        return true;
    }

'''
    if "xr_vk_record_indexed_draw" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan indexed draw: shader-module helper marker not found")
        if "xr_vk_bind_stream_geometry" not in text:
            raise RuntimeError("Vulkan indexed draw: stream geometry bind helper not materialized")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_indexed_draw_packet",
        "VkPipeline pipeline",
        "VkDeviceSize vertex_offset",
        "VkDeviceSize index_offset",
        "VkIndexType index_type",
        "u32 index_count",
        "bool xr_vk_record_indexed_draw",
        "xr_vk_bind_stream_geometry(command_buffer",
        "g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, draw.pipeline)",
        "g_vkCmdDrawIndexed(command_buffer, draw.index_count, 1, draw.first_index, draw.vertex_offset_bias, 0)",
        "bool xr_vk_make_indexed_draw_packet",
        "xr_vk_d3d_index_format_to_type",
        "xr_vk_primitive_element_count(D3DPT_TRIANGLELIST",
        "static_cast<VkDeviceSize>(start_index) * index_stride",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan indexed draw validation failed: missing {token}")

    print("[vulkan-indexed-draw] validated D3D9 indexed draw packet + Vulkan bind/draw recording installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install safe indexed Vulkan draw recording over mirrored SHOC geometry streams.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_indexed_draw(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
