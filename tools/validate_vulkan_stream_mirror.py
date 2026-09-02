from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "VkBuffer g_stream_vertex_buffer = VK_NULL_HANDLE",
        "VkDeviceMemory g_stream_vertex_memory = VK_NULL_HANDLE",
        "VkDeviceSize g_stream_vertex_capacity = 0",
        "VkBuffer g_stream_index_buffer = VK_NULL_HANDLE",
        "VkDeviceMemory g_stream_index_memory = VK_NULL_HANDLE",
        "VkDeviceSize g_stream_index_capacity = 0",
        "void xr_vk_destroy_stream_buffer",
        "bool xr_vk_resize_host_stream",
        "VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT",
        "bool xr_vk_upload_host_stream",
        "static_cast<VkDeviceSize>(byte_offset) + byte_count",
        "bool xr_vk_upload_vertex_stream",
        "VK_BUFFER_USAGE_VERTEX_BUFFER_BIT",
        "bool xr_vk_upload_index_stream",
        "VK_BUFFER_USAGE_INDEX_BUFFER_BIT",
        "bool xr_vk_bind_stream_geometry",
        "g_vkCmdBindVertexBuffers(command_buffer, 0, 1",
        "g_vkCmdBindIndexBuffer(command_buffer, g_stream_index_buffer",
        "xr_vk_destroy_stream_buffer(g_stream_vertex_buffer",
        "xr_vk_destroy_stream_buffer(g_stream_index_buffer",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan stream mirror validation failed: missing {token}")

    resize_pos = text.find("bool xr_vk_resize_host_stream")
    upload_pos = text.find("bool xr_vk_upload_host_stream")
    vertex_pos = text.find("bool xr_vk_upload_vertex_stream")
    index_pos = text.find("bool xr_vk_upload_index_stream")
    bind_pos = text.find("bool xr_vk_bind_stream_geometry")
    if min(resize_pos, upload_pos, vertex_pos, index_pos, bind_pos) < 0 or not (
        resize_pos < upload_pos < vertex_pos < index_pos < bind_pos
    ):
        raise RuntimeError("Vulkan stream mirror validation failed: helper order is inconsistent")

    destroy_frame = text.find("void xr_vk_destroy_frame_resources()")
    destroy_vertex = text.find("xr_vk_destroy_stream_buffer(g_stream_vertex_buffer", destroy_frame)
    destroy_index = text.find("xr_vk_destroy_stream_buffer(g_stream_index_buffer", destroy_frame)
    if destroy_frame < 0 or destroy_vertex < destroy_frame or destroy_index < destroy_vertex:
        raise RuntimeError("Vulkan stream mirror validation failed: stream buffers are not released with frame resources")

    print("[vulkan-stream-check] host-visible dynamic vertex/index mirrors and lifecycle cleanup verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate materialized Vulkan dynamic geometry stream mirrors.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())