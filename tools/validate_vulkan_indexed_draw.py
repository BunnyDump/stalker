from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_indexed_draw_packet",
        "bool xr_vk_make_indexed_draw_packet",
        "bool xr_vk_record_indexed_draw",
        "xr_vk_d3d_index_format_to_type(index_format, index_type, index_stride)",
        "xr_vk_primitive_element_count(D3DPT_TRIANGLELIST, primitive_count, index_count)",
        "xr_vk_bind_stream_geometry(command_buffer, draw.vertex_offset, draw.index_offset, draw.index_type)",
        "g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, draw.pipeline)",
        "g_vkCmdDrawIndexed(command_buffer, draw.index_count, 1, draw.first_index, draw.vertex_offset_bias, 0)",
        "absolute_index_offset < index_stream_offset",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan indexed draw validation failed: missing {token}")

    record_pos = text.find("bool xr_vk_record_indexed_draw")
    stream_bind_pos = text.find("xr_vk_bind_stream_geometry(command_buffer", record_pos)
    pipeline_bind_pos = text.find("g_vkCmdBindPipeline(command_buffer", record_pos)
    draw_pos = text.find("g_vkCmdDrawIndexed(command_buffer", record_pos)
    if min(record_pos, stream_bind_pos, pipeline_bind_pos, draw_pos) < 0:
        raise RuntimeError("Vulkan indexed draw validation failed: record section incomplete")
    if not (record_pos < stream_bind_pos < pipeline_bind_pos < draw_pos):
        raise RuntimeError("Vulkan indexed draw validation failed: bind/draw order is inconsistent")

    if "g_vkCmdDrawIndexed(command_buffer, draw.index_count, 0," in text:
        raise RuntimeError("Vulkan indexed draw validation failed: zero instance count")

    print("[vulkan-indexed-draw-check] stream binding + graphics pipeline binding + indexed draw ordering verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate materialized Vulkan indexed draw packet recording.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
