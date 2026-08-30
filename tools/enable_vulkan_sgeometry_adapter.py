from __future__ import annotations

import argparse
from pathlib import Path


def install_sgeometry_adapter(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan SGeometry adapter requires materialized geometry bridge")

    text = source.read_text(encoding="utf-8")

    include_marker = '#include "vk_bootstrap.h"\n'
    if '#include "../Shader.h"' not in text:
        if include_marker not in text:
            raise RuntimeError("Vulkan SGeometry adapter: bootstrap include marker not found")
        text = text.replace(include_marker, include_marker + '#include "../Shader.h"\n', 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    bool xr_vk_d3d_primitive_to_topology(D3DPRIMITIVETYPE primitive, VkPrimitiveTopology& topology)
    {
        switch (primitive)
        {
        case D3DPT_POINTLIST: topology = VK_PRIMITIVE_TOPOLOGY_POINT_LIST; return true;
        case D3DPT_LINELIST: topology = VK_PRIMITIVE_TOPOLOGY_LINE_LIST; return true;
        case D3DPT_LINESTRIP: topology = VK_PRIMITIVE_TOPOLOGY_LINE_STRIP; return true;
        case D3DPT_TRIANGLELIST: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; return true;
        case D3DPT_TRIANGLESTRIP: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP; return true;
        case D3DPT_TRIANGLEFAN: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN; return true;
        default: return false;
        }
    }

    bool xr_vk_d3d_index_format_to_type(D3DFORMAT format, VkIndexType& index_type, u32& index_stride)
    {
        switch (format)
        {
        case D3DFMT_INDEX16:
            index_type = VK_INDEX_TYPE_UINT16;
            index_stride = sizeof(u16);
            return true;
        case D3DFMT_INDEX32:
            index_type = VK_INDEX_TYPE_UINT32;
            index_stride = sizeof(u32);
            return true;
        default:
            return false;
        }
    }

    bool xr_vk_primitive_element_count(D3DPRIMITIVETYPE primitive, u32 primitive_count, u32& element_count)
    {
        if (!primitive_count)
        {
            element_count = 0;
            return true;
        }
        switch (primitive)
        {
        case D3DPT_POINTLIST: element_count = primitive_count; return true;
        case D3DPT_LINELIST: element_count = primitive_count * 2; return true;
        case D3DPT_LINESTRIP: element_count = primitive_count + 1; return true;
        case D3DPT_TRIANGLELIST: element_count = primitive_count * 3; return true;
        case D3DPT_TRIANGLESTRIP:
        case D3DPT_TRIANGLEFAN: element_count = primitive_count + 2; return true;
        default: return false;
        }
    }

    bool xr_vk_build_sgeometry_layout(const SGeometry* geometry, D3DPRIMITIVETYPE primitive,
        xr_vk_vertex_input_layout& vertex_input, VkPrimitiveTopology& topology)
    {
        if (!geometry || !geometry->dcl._get() || !geometry->vb || !geometry->vb_stride)
            return false;

        const SDeclaration* declaration = geometry->dcl._get();
        const u32 declaration_count = static_cast<u32>(declaration->dcl_code.size());
        if (!declaration_count || declaration_count > MAX_FVF_DECL_SIZE)
            return false;
        if (!xr_vk_build_vertex_input_layout(&declaration->dcl_code[0], declaration_count,
            geometry->vb_stride, vertex_input))
            return false;
        return xr_vk_d3d_primitive_to_topology(primitive, topology);
    }

'''
    if "xr_vk_build_sgeometry_layout" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan SGeometry adapter: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    signature = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout)
'''
    replacement = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout, VkPrimitiveTopology topology)
'''
    if "const xr_vk_vertex_input_layout* vertex_layout, VkPrimitiveTopology topology" not in text:
        if signature not in text:
            raise RuntimeError("Vulkan SGeometry adapter: graphics-pipeline signature marker not found")
        text = text.replace(signature, replacement, 1)

    topology_marker = "        input_assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;\n"
    topology_replacement = '''        if (topology < VK_PRIMITIVE_TOPOLOGY_POINT_LIST || topology > VK_PRIMITIVE_TOPOLOGY_PATCH_LIST)
            return VK_NULL_HANDLE;
        input_assembly.topology = topology;
'''
    if "input_assembly.topology = topology;" not in text:
        if topology_marker not in text:
            raise RuntimeError("Vulkan SGeometry adapter: hard-coded topology marker not found")
        text = text.replace(topology_marker, topology_replacement, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        '#include "../Shader.h"',
        "xr_vk_d3d_primitive_to_topology",
        "D3DPT_TRIANGLELIST",
        "VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST",
        "D3DPT_TRIANGLESTRIP",
        "VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP",
        "D3DPT_TRIANGLEFAN",
        "VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN",
        "xr_vk_d3d_index_format_to_type",
        "D3DFMT_INDEX16",
        "VK_INDEX_TYPE_UINT16",
        "D3DFMT_INDEX32",
        "VK_INDEX_TYPE_UINT32",
        "xr_vk_primitive_element_count",
        "primitive_count * 3",
        "primitive_count + 2",
        "xr_vk_build_sgeometry_layout",
        "geometry->dcl._get()",
        "declaration_count = static_cast<u32>(declaration->dcl_code.size())",
        "declaration_count > MAX_FVF_DECL_SIZE",
        "&declaration->dcl_code[0], declaration_count",
        "geometry->vb_stride",
        "VkPrimitiveTopology topology",
        "input_assembly.topology = topology",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan SGeometry adapter validation failed: missing {token}")

    print("[vulkan-sgeometry] bounded native SGeometry + primitive topology + D3D index metadata translation installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt native SHOC SGeometry and indexed draw metadata into Vulkan state.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_sgeometry_adapter(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())