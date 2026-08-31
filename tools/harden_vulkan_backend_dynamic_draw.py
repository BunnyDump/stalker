from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    indexed_export = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'
    plain_export = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw('
    indexed_start = text.find(indexed_export)
    plain_start = text.find(plain_export, indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan backend dynamic draw: backend exports not found")

    helpers = r'''    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,
        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,
        IDirect3DIndexBuffer9* index_buffer, u32 vertex_stride, u32 base_vertex,
        u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)
    {
        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_buffer ||
            !index_buffer || !vertex_stride || !vertex_count || !primitive_count ||
            base_vertex > 0x7fffffffu || start_vertex > 0xffffffffu - base_vertex)
            return false;

        u32 index_count = 0;
        if (!xr_vk_primitive_element_count(primitive, primitive_count, index_count) || !index_count)
            return false;

        const u32 first_vertex = base_vertex + start_vertex;
        VkDeviceSize validated_vertex_offset = 0;
        VkDeviceSize validated_index_offset = 0;
        if (!xr_vk_dynamic_vertex_range_ready(vertex_buffer, first_vertex, vertex_count,
                vertex_stride, validated_vertex_offset) ||
            !xr_vk_dynamic_index_range_ready(index_buffer, start_index, index_count, validated_index_offset))
            return false;

        // The mirror preserves the original D3D byte offsets, so bind the mirrored VB at zero
        // and keep D3D9 BaseVertexIndex as Vulkan vertexOffset.  MinVertexIndex/start_vertex is
        // only a range hint and must not be folded into the Vulkan binding offset.
        xr_vk_indexed_draw_packet draw = {};
        if (!xr_vk_make_indexed_draw_packet(pipeline, D3DFMT_INDEX16, primitive, start_index,
                primitive_count, static_cast<s32>(base_vertex), 0, 0, draw))
            return false;
        return xr_vk_record_indexed_draw(command_buffer, draw);
    }

    bool xr_vk_record_dynamic_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,
        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
        u32 start_vertex, u32 primitive_count)
    {
        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_buffer ||
            !vertex_stride || !primitive_count || !g_vkCmdBindPipeline ||
            !g_vkCmdBindVertexBuffers || !g_vkCmdDraw || g_stream_vertex_buffer == VK_NULL_HANDLE)
            return false;

        u32 vertex_count = 0;
        if (!xr_vk_primitive_element_count(primitive, primitive_count, vertex_count) || !vertex_count)
            return false;

        VkDeviceSize validated_vertex_offset = 0;
        if (!xr_vk_dynamic_vertex_range_ready(vertex_buffer, start_vertex, vertex_count,
                vertex_stride, validated_vertex_offset))
            return false;

        const VkBuffer vertex = g_stream_vertex_buffer;
        const VkDeviceSize bind_offset = 0;
        g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vertex, &bind_offset);
        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);
        return true;
    }

'''
    if "xr_vk_record_dynamic_indexed_backend_draw" not in text:
        text = text[:indexed_start] + helpers + text[indexed_start:]

    # Re-resolve export offsets after helper insertion.
    indexed_start = text.find(indexed_export)
    plain_start = text.find(plain_export, indexed_start)
    indexed = text[indexed_start:plain_start]

    indexed_success = r'''

    if (xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;'''
    if "xr_vk_record_dynamic_indexed_backend_draw(command_buffer" not in indexed:
        fallback = indexed.rfind("    return FALSE;")
        if fallback < 0:
            raise RuntimeError("Vulkan backend dynamic draw: indexed final fallback not found")
        indexed = indexed[:fallback] + indexed_success + "\n" + indexed[fallback:]
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find(plain_export, indexed_start)
    plain = text[plain_start:]
    plain_success = r'''

    if (xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;'''
    if "xr_vk_record_dynamic_backend_draw(command_buffer" not in plain:
        fallback = plain.rfind("    return FALSE;")
        if fallback < 0:
            raise RuntimeError("Vulkan backend dynamic draw: plain final fallback not found")
        plain = plain[:fallback] + plain_success + "\n" + plain[fallback:]
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "xr_vk_record_dynamic_indexed_backend_draw",
        "xr_vk_dynamic_vertex_range_ready(vertex_buffer, first_vertex, vertex_count",
        "xr_vk_dynamic_index_range_ready(index_buffer, start_index, index_count",
        "xr_vk_make_indexed_draw_packet(pipeline, D3DFMT_INDEX16",
        "xr_vk_record_indexed_draw(command_buffer, draw)",
        "xr_vk_record_dynamic_backend_draw",
        "g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vertex, &bind_offset)",
        "g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline)",
        "g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0)",
        "return TRUE;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend dynamic draw validation failed: missing {token}")

    print("[vulkan-backend-dynamic-draw] live CBackend dynamic VB/IB draws now record into the active Vulkan command buffer; unsupported/static geometry remains fail-closed on D3D9")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute mirrored SHOC dynamic CBackend draws on the live Vulkan command buffer while preserving safe D3D9 fallback.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
