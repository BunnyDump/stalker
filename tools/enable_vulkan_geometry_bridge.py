from __future__ import annotations

import argparse
from pathlib import Path


def install_geometry_bridge(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan geometry bridge requires materialized pipeline source")

    text = source.read_text(encoding="utf-8")

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    struct xr_vk_vertex_input_layout
    {
        VkVertexInputBindingDescription bindings[1];
        VkVertexInputAttributeDescription attributes[MAX_FVF_DECL_SIZE];
        u32 binding_count;
        u32 attribute_count;
    };

    VkFormat xr_vk_d3d_decl_type_to_format(BYTE type)
    {
        switch (type)
        {
        case D3DDECLTYPE_FLOAT1: return VK_FORMAT_R32_SFLOAT;
        case D3DDECLTYPE_FLOAT2: return VK_FORMAT_R32G32_SFLOAT;
        case D3DDECLTYPE_FLOAT3: return VK_FORMAT_R32G32B32_SFLOAT;
        case D3DDECLTYPE_FLOAT4: return VK_FORMAT_R32G32B32A32_SFLOAT;
        case D3DDECLTYPE_D3DCOLOR: return VK_FORMAT_B8G8R8A8_UNORM;
        case D3DDECLTYPE_UBYTE4: return VK_FORMAT_R8G8B8A8_UINT;
        case D3DDECLTYPE_SHORT2: return VK_FORMAT_R16G16_SINT;
        case D3DDECLTYPE_SHORT4: return VK_FORMAT_R16G16B16A16_SINT;
        case D3DDECLTYPE_UBYTE4N: return VK_FORMAT_R8G8B8A8_UNORM;
        case D3DDECLTYPE_SHORT2N: return VK_FORMAT_R16G16_SNORM;
        case D3DDECLTYPE_SHORT4N: return VK_FORMAT_R16G16B16A16_SNORM;
        case D3DDECLTYPE_USHORT2N: return VK_FORMAT_R16G16_UNORM;
        case D3DDECLTYPE_USHORT4N: return VK_FORMAT_R16G16B16A16_UNORM;
        case D3DDECLTYPE_UDEC3: return VK_FORMAT_A2B10G10R10_UINT_PACK32;
        case D3DDECLTYPE_DEC3N: return VK_FORMAT_A2B10G10R10_SNORM_PACK32;
        case D3DDECLTYPE_FLOAT16_2: return VK_FORMAT_R16G16_SFLOAT;
        case D3DDECLTYPE_FLOAT16_4: return VK_FORMAT_R16G16B16A16_SFLOAT;
        default: return VK_FORMAT_UNDEFINED;
        }
    }

    u32 xr_vk_d3d_decl_type_size(BYTE type)
    {
        switch (type)
        {
        case D3DDECLTYPE_FLOAT1: return 4;
        case D3DDECLTYPE_FLOAT2: return 8;
        case D3DDECLTYPE_FLOAT3: return 12;
        case D3DDECLTYPE_FLOAT4: return 16;
        case D3DDECLTYPE_D3DCOLOR:
        case D3DDECLTYPE_UBYTE4:
        case D3DDECLTYPE_UBYTE4N:
        case D3DDECLTYPE_UDEC3:
        case D3DDECLTYPE_DEC3N: return 4;
        case D3DDECLTYPE_SHORT2:
        case D3DDECLTYPE_SHORT2N:
        case D3DDECLTYPE_USHORT2N:
        case D3DDECLTYPE_FLOAT16_2: return 4;
        case D3DDECLTYPE_SHORT4:
        case D3DDECLTYPE_SHORT4N:
        case D3DDECLTYPE_USHORT4N:
        case D3DDECLTYPE_FLOAT16_4: return 8;
        default: return 0;
        }
    }

    bool xr_vk_build_vertex_input_layout(const D3DVERTEXELEMENT9* decl, u32 decl_count, u32 stride,
        xr_vk_vertex_input_layout& out)
    {
        ZeroMemory(&out, sizeof(out));
        if (!decl || !decl_count || decl_count > MAX_FVF_DECL_SIZE || !stride)
            return false;

        out.binding_count = 1;
        out.bindings[0].binding = 0;
        out.bindings[0].stride = stride;
        out.bindings[0].inputRate = VK_VERTEX_INPUT_RATE_VERTEX;

        bool terminated = false;
        for (u32 i = 0; i < decl_count; ++i)
        {
            const D3DVERTEXELEMENT9& element = decl[i];
            if (element.Stream == 0xff && element.Type == D3DDECLTYPE_UNUSED)
            {
                terminated = true;
                break;
            }
            // SHOC SGeometry owns one D3D9 vertex buffer and binds it as stream zero.
            // Reject unsupported multi-stream declarations instead of silently corrupting input.
            if (element.Stream != 0 || element.Method != D3DDECLMETHOD_DEFAULT)
                return false;

            const VkFormat format = xr_vk_d3d_decl_type_to_format(element.Type);
            const u32 element_size = xr_vk_d3d_decl_type_size(element.Type);
            if (format == VK_FORMAT_UNDEFINED || !element_size ||
                static_cast<u32>(element.Offset) + element_size > stride ||
                out.attribute_count >= MAX_FVF_DECL_SIZE)
                return false;

            VkVertexInputAttributeDescription& attribute = out.attributes[out.attribute_count];
            attribute.location = out.attribute_count;
            attribute.binding = 0;
            attribute.format = format;
            attribute.offset = element.Offset;
            ++out.attribute_count;
        }
        return terminated && out.attribute_count != 0;
    }

'''
    if "xr_vk_build_vertex_input_layout" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan geometry bridge: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    signature = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry)
'''
    replacement = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout)
'''
    if "const xr_vk_vertex_input_layout* vertex_layout" not in text:
        if signature not in text:
            raise RuntimeError("Vulkan geometry bridge: graphics-pipeline signature marker not found")
        text = text.replace(signature, replacement, 1)

    vertex_marker = '''        VkPipelineVertexInputStateCreateInfo vertex_input = {};
        vertex_input.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO;
'''
    vertex_replacement = vertex_marker + '''        if (vertex_layout)
        {
            vertex_input.vertexBindingDescriptionCount = vertex_layout->binding_count;
            vertex_input.pVertexBindingDescriptions = vertex_layout->bindings;
            vertex_input.vertexAttributeDescriptionCount = vertex_layout->attribute_count;
            vertex_input.pVertexAttributeDescriptions = vertex_layout->attributes;
        }
'''
    if "vertex_input.vertexBindingDescriptionCount" not in text:
        if vertex_marker not in text:
            raise RuntimeError("Vulkan geometry bridge: vertex-input state marker not found")
        text = text.replace(vertex_marker, vertex_replacement, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_vertex_input_layout",
        "xr_vk_d3d_decl_type_to_format",
        "xr_vk_d3d_decl_type_size",
        "D3DDECLTYPE_FLOAT3",
        "D3DDECLTYPE_D3DCOLOR",
        "D3DDECLTYPE_FLOAT16_4",
        "xr_vk_build_vertex_input_layout",
        "u32 decl_count",
        "decl_count > MAX_FVF_DECL_SIZE",
        "static_cast<u32>(element.Offset) + element_size > stride",
        "return terminated && out.attribute_count != 0",
        "element.Offset",
        "vertexBindingDescriptionCount",
        "vertexAttributeDescriptionCount",
        "const xr_vk_vertex_input_layout* vertex_layout",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan geometry bridge validation failed: missing {token}")
    print("[vulkan-geometry] bounded D3D9 declaration -> Vulkan binding/attribute translation installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the transitional SHOC D3D9 geometry declaration to Vulkan vertex-input bridge.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_geometry_bridge(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())