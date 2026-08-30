from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_vertex_input_layout",
        "VkVertexInputBindingDescription bindings[1]",
        "VkVertexInputAttributeDescription attributes[MAX_FVF_DECL_SIZE]",
        "VkFormat xr_vk_d3d_decl_type_to_format",
        "D3DDECLTYPE_FLOAT1",
        "D3DDECLTYPE_FLOAT2",
        "D3DDECLTYPE_FLOAT3",
        "D3DDECLTYPE_FLOAT4",
        "D3DDECLTYPE_D3DCOLOR",
        "D3DDECLTYPE_UBYTE4N",
        "D3DDECLTYPE_SHORT4N",
        "D3DDECLTYPE_FLOAT16_4",
        "bool xr_vk_build_vertex_input_layout",
        "element.Stream != 0",
        "element.Method != D3DDECLMETHOD_DEFAULT",
        "attribute.location = out.attribute_count",
        "attribute.offset = element.Offset",
        "const xr_vk_vertex_input_layout* vertex_layout",
        "vertex_input.vertexBindingDescriptionCount = vertex_layout->binding_count",
        "vertex_input.pVertexBindingDescriptions = vertex_layout->bindings",
        "vertex_input.vertexAttributeDescriptionCount = vertex_layout->attribute_count",
        "vertex_input.pVertexAttributeDescriptions = vertex_layout->attributes",
        '#include "../Shader.h"',
        "bool xr_vk_d3d_primitive_to_topology",
        "D3DPT_POINTLIST",
        "D3DPT_LINELIST",
        "D3DPT_LINESTRIP",
        "D3DPT_TRIANGLELIST",
        "D3DPT_TRIANGLESTRIP",
        "D3DPT_TRIANGLEFAN",
        "bool xr_vk_d3d_index_format_to_type",
        "D3DFMT_INDEX16",
        "VK_INDEX_TYPE_UINT16",
        "D3DFMT_INDEX32",
        "VK_INDEX_TYPE_UINT32",
        "bool xr_vk_primitive_element_count",
        "element_count = primitive_count * 3",
        "element_count = primitive_count + 2",
        "bool xr_vk_build_sgeometry_layout",
        "geometry->dcl._get()",
        "declaration->dcl_code.empty()",
        "&declaration->dcl_code[0]",
        "geometry->vb_stride",
        "const xr_vk_vertex_input_layout* vertex_layout, VkPrimitiveTopology topology",
        "input_assembly.topology = topology",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan geometry bridge validation failed: missing {token}")

    forbidden = (
        "vertex_input.vertexBindingDescriptionCount = 0;",
        "vertex_input.vertexAttributeDescriptionCount = 0;",
        "input_assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;",
    )
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"Vulkan geometry bridge validation failed: stale fixed state {token}")

    build_pos = text.find("bool xr_vk_build_vertex_input_layout")
    topology_pos = text.find("bool xr_vk_d3d_primitive_to_topology")
    index_pos = text.find("bool xr_vk_d3d_index_format_to_type")
    count_pos = text.find("bool xr_vk_primitive_element_count")
    sgeometry_pos = text.find("bool xr_vk_build_sgeometry_layout")
    pipeline_pos = text.find("VkPipeline xr_vk_create_graphics_pipeline")
    vertex_state_pos = text.find("vertex_input.vertexBindingDescriptionCount", pipeline_pos)
    topology_state_pos = text.find("input_assembly.topology = topology", pipeline_pos)
    graphics_info_pos = text.find("VkGraphicsPipelineCreateInfo info", pipeline_pos)
    if min(build_pos, topology_pos, index_pos, count_pos, sgeometry_pos, pipeline_pos, vertex_state_pos, topology_state_pos, graphics_info_pos) < 0:
        raise RuntimeError("Vulkan geometry bridge validation failed: expected sections not found")
    if not (build_pos < topology_pos < index_pos < count_pos < sgeometry_pos < pipeline_pos < vertex_state_pos < topology_state_pos < graphics_info_pos):
        raise RuntimeError("Vulkan geometry bridge validation failed: materialized section order is inconsistent")

    print("[vulkan-geometry-check] D3D9 declaration + SGeometry + topology + indexed draw metadata wiring verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the materialized SHOC D3D9/SGeometry -> Vulkan draw bridge.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
