from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    backend = root / "xr_3da" / "R_Backend_Runtime.h"
    for path in (source, backend):
        if not path.is_file():
            raise FileNotFoundError(path)

    text = source.read_text(encoding="utf-8")
    runtime = backend.read_text(encoding="utf-8")

    required = (
        "bool xr_vk_record_dynamic_indexed_backend_draw",
        "VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive",
        "base_vertex > 0x7fffffffu",
        "start_vertex > 0xffffffffu - base_vertex",
        "xr_vk_primitive_element_count(primitive, primitive_count, index_count)",
        "const u32 first_vertex = base_vertex + start_vertex;",
        "xr_vk_dynamic_vertex_range_ready(vertex_buffer, first_vertex, vertex_count",
        "xr_vk_dynamic_index_range_ready(index_buffer, start_index, index_count",
        "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive",
        "static_cast<s32>(base_vertex), 0, 0, draw",
        "xr_vk_record_indexed_draw(command_buffer, draw)",
        "bool xr_vk_record_dynamic_backend_draw",
        "descriptor_set == VK_NULL_HANDLE",
        "xr_vk_dynamic_vertex_range_ready(vertex_buffer, start_vertex, vertex_count",
        "const VkDeviceSize bind_offset = 0;",
        "g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vertex, &bind_offset)",
        "g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline)",
        "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)",
        "g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0)",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan backend dynamic draw validation failed: missing {token}")

    if "bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, VkDescriptorSet descriptor_set" not in text:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: descriptor-aware packet factory missing")
    if "D3DFORMAT index_format, D3DPRIMITIVETYPE primitive_type" not in text:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: primitive topology was dropped from descriptor-aware factory")
    if "xr_vk_make_indexed_draw_packet(pipeline, VK_NULL_HANDLE" in text:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: indexed production draw still passes a null descriptor")

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: exports missing")

    indexed = text[indexed_start:plain_start]
    plain = text[plain_start:]
    indexed_gate = indexed.find("xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count")
    indexed_call = indexed.find("xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive", indexed_gate)
    indexed_true = indexed.find("return TRUE;", indexed_call)
    indexed_fallback = indexed.rfind("return FALSE;")
    if min(indexed_gate, indexed_call, indexed_true, indexed_fallback) < 0 or not indexed_gate < indexed_call < indexed_true < indexed_fallback:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: indexed descriptor/gate/success/fallback order invalid")

    plain_gate = plain.find("xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count")
    plain_call = plain.find("xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive", plain_gate)
    plain_true = plain.find("return TRUE;", plain_call)
    plain_fallback = plain.rfind("return FALSE;")
    if min(plain_gate, plain_call, plain_true, plain_fallback) < 0 or not plain_gate < plain_call < plain_true < plain_fallback:
        raise RuntimeError("Vulkan backend dynamic draw validation failed: plain descriptor/gate/success/fallback order invalid")

    for token in (
        "HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC)",
        "HW.pDevice->DrawPrimitive(T, startV, PC)",
    ):
        if token not in runtime:
            raise RuntimeError(f"Vulkan backend dynamic draw validation failed: D3D9 fallback removed: {token}")

    print("[vulkan-backend-dynamic-draw] live descriptor-aware topology-preserving packet ABI + exact ranges + D3D9 fallback verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production Vulkan recording for descriptor-backed mirrored SHOC dynamic draws.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
