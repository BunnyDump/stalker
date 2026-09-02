from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    state_marker = "    xr_vector<xr_vk_pipeline_record> g_graphics_pipelines;\n"
    state_block = state_marker + r'''

    struct xr_vk_shader_spirv_record
    {
        xr_string name;
        bool vertex_stage;
        xr_vector<u8> bytes;
    };

    struct xr_vk_shader_pipeline_key
    {
        IDirect3DVertexShader9* vertex_shader;
        IDirect3DPixelShader9* pixel_shader;
        IDirect3DVertexDeclaration9* declaration;
        xr_string vertex_shader_name;
        xr_string pixel_shader_name;
        D3DPRIMITIVETYPE primitive;
        u32 vertex_stride;
        u64 render_state_identity;
        u64 render_pass_generation;
    };

    struct xr_vk_shader_pipeline_cache_entry
    {
        xr_vk_shader_pipeline_key key;
        VkPipeline pipeline;
    };

    xr_vector<xr_vk_shader_spirv_record> g_shader_spirv_registry;
    xr_vector<xr_vk_shader_pipeline_cache_entry> g_shader_pipeline_cache;
'''
    if "struct xr_vk_shader_pipeline_key" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan shader pipeline cache: pipeline generation state marker not found")
        text = text.replace(state_marker, state_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    const xr_vk_shader_spirv_record* xr_vk_find_shader_spirv(const char* name, bool vertex_stage)
    {
        if (!name || !*name)
            return NULL;
        for (u32 i = 0; i < g_shader_spirv_registry.size(); ++i)
        {
            const xr_vk_shader_spirv_record& record = g_shader_spirv_registry[i];
            if (record.vertex_stage == vertex_stage && record.name == name && !record.bytes.empty())
                return &record;
        }
        return NULL;
    }

    bool xr_vk_shader_pipeline_key_equal(const xr_vk_shader_pipeline_key& a, const xr_vk_shader_pipeline_key& b)
    {
        return a.vertex_shader == b.vertex_shader && a.pixel_shader == b.pixel_shader &&
            a.declaration == b.declaration && a.vertex_shader_name == b.vertex_shader_name &&
            a.pixel_shader_name == b.pixel_shader_name && a.primitive == b.primitive &&
            a.vertex_stride == b.vertex_stride && a.render_state_identity == b.render_state_identity &&
            a.render_pass_generation == b.render_pass_generation;
    }

    void xr_vk_clear_shader_pipeline_cache()
    {
        for (u32 i = 0; i < g_shader_pipeline_cache.size(); ++i)
        {
            VkPipeline pipeline = g_shader_pipeline_cache[i].pipeline;
            if (pipeline != VK_NULL_HANDLE)
                xr_vk_destroy_pipeline_handle(pipeline);
        }
        g_shader_pipeline_cache.clear();
    }

    bool xr_vk_copy_d3d_declaration(IDirect3DVertexDeclaration9* declaration, D3DVERTEXELEMENT9 (&elements)[MAX_FVF_DECL_SIZE], u32& count)
    {
        count = 0;
        if (!declaration)
            return false;
        UINT native_count = MAX_FVF_DECL_SIZE;
        HRESULT hr = declaration->GetDeclaration(elements, &native_count);
        if (FAILED(hr) || !native_count || native_count > MAX_FVF_DECL_SIZE)
            return false;
        count = static_cast<u32>(native_count);
        return true;
    }

    VkPipeline xr_vk_resolve_shader_pipeline(IDirect3DVertexShader9* vertex_shader,
        IDirect3DPixelShader9* pixel_shader, const char* vertex_shader_name, const char* pixel_shader_name,
        IDirect3DVertexDeclaration9* declaration, u32 vertex_stride, D3DPRIMITIVETYPE primitive,
        const xr_vk_render_state_snapshot* render_state)
    {
        if (!vertex_shader || !pixel_shader || !vertex_shader_name || !*vertex_shader_name ||
            !pixel_shader_name || !*pixel_shader_name || !declaration || !vertex_stride ||
            !render_state || !render_state->identity || !g_render_pass_generation)
            return VK_NULL_HANDLE;

        xr_vk_shader_pipeline_key key;
        key.vertex_shader = vertex_shader;
        key.pixel_shader = pixel_shader;
        key.declaration = declaration;
        key.vertex_shader_name = vertex_shader_name;
        key.pixel_shader_name = pixel_shader_name;
        key.primitive = primitive;
        key.vertex_stride = vertex_stride;
        key.render_state_identity = render_state->identity;
        key.render_pass_generation = g_render_pass_generation;

        for (u32 i = 0; i < g_shader_pipeline_cache.size(); ++i)
            if (xr_vk_shader_pipeline_key_equal(g_shader_pipeline_cache[i].key, key) &&
                xr_vk_pipeline_is_current(g_shader_pipeline_cache[i].pipeline))
                return g_shader_pipeline_cache[i].pipeline;

        const xr_vk_shader_spirv_record* vs = xr_vk_find_shader_spirv(vertex_shader_name, true);
        const xr_vk_shader_spirv_record* ps = xr_vk_find_shader_spirv(pixel_shader_name, false);
        if (!vs || !ps)
            return VK_NULL_HANDLE;

        D3DVERTEXELEMENT9 elements[MAX_FVF_DECL_SIZE] = {};
        u32 element_count = 0;
        xr_vk_vertex_input_layout vertex_layout;
        VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_MAX_ENUM;
        if (!xr_vk_copy_d3d_declaration(declaration, elements, element_count) ||
            !xr_vk_build_vertex_input_layout(elements, element_count, vertex_stride, vertex_layout) ||
            !xr_vk_d3d_primitive_to_topology(primitive, topology))
            return VK_NULL_HANDLE;

        VkPipeline pipeline = xr_vk_create_graphics_pipeline(&vs->bytes[0], vs->bytes.size(), "main",
            &ps->bytes[0], ps->bytes.size(), "main", &vertex_layout, topology, render_state);
        if (pipeline == VK_NULL_HANDLE)
            return VK_NULL_HANDLE;

        xr_vk_shader_pipeline_cache_entry entry;
        entry.key = key;
        entry.pipeline = pipeline;
        g_shader_pipeline_cache.push_back(entry);
        return pipeline;
    }

'''
    if "xr_vk_resolve_shader_pipeline" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan shader pipeline cache: shader helper marker not found")
        if "xr_vk_destroy_pipeline_handle" not in text or "xr_vk_build_vertex_input_layout" not in text or "xr_vk_d3d_primitive_to_topology" not in text:
            raise RuntimeError("Vulkan shader pipeline cache: prerequisite helpers are not materialized")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    # Full shutdown owns shader registry/cache lifetime. Cache entries must be removed
    # before the generic pipeline owner destroys remaining pipelines.
    destroy_start = text.find("void xr_vk_destroy_frame_resources()")
    destroy_end = text.find("void xr_vk_destroy_window_runtime()", destroy_start)
    if destroy_start < 0 or destroy_end < 0:
        raise RuntimeError("Vulkan shader pipeline cache: full teardown function not found")
    destroy = text[destroy_start:destroy_end]
    idle_marker = "        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)\n            g_vkDeviceWaitIdle(g_device);\n"
    if "xr_vk_clear_shader_pipeline_cache();" not in destroy:
        if idle_marker not in destroy:
            raise RuntimeError("Vulkan shader pipeline cache: shutdown idle marker not found")
        destroy = destroy.replace(idle_marker, idle_marker + "        xr_vk_clear_shader_pipeline_cache();\n        g_shader_spirv_registry.clear();\n", 1)
        text = text[:destroy_start] + destroy + text[destroy_end:]

    exports = r'''

extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_shader_spirv(
    LPCSTR shader_name, BOOL vertex_stage, const void* spirv_data, u32 spirv_size)
{
    if (!shader_name || !*shader_name || !spirv_data || spirv_size < 20 || (spirv_size & 3))
        return FALSE;
    const u32* words = static_cast<const u32*>(spirv_data);
    if (words[0] != 0x07230203u)
        return FALSE;

    for (u32 i = 0; i < g_shader_spirv_registry.size(); ++i)
    {
        xr_vk_shader_spirv_record& record = g_shader_spirv_registry[i];
        if (record.name == shader_name && record.vertex_stage == (vertex_stage != FALSE))
        {
            record.bytes.resize(spirv_size);
            CopyMemory(&record.bytes[0], spirv_data, spirv_size);
            xr_vk_clear_shader_pipeline_cache();
            return TRUE;
        }
    }

    xr_vk_shader_spirv_record record;
    record.name = shader_name;
    record.vertex_stage = vertex_stage != FALSE;
    record.bytes.resize(spirv_size);
    CopyMemory(&record.bytes[0], spirv_data, spirv_size);
    g_shader_spirv_registry.push_back(record);
    return TRUE;
}
'''
    if "xrRender_vk_register_shader_spirv" not in text:
        text += exports

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_shader_spirv_record",
        "struct xr_vk_shader_pipeline_key",
        "g_shader_spirv_registry",
        "g_shader_pipeline_cache",
        "xr_vk_find_shader_spirv",
        "xr_vk_shader_pipeline_key_equal",
        "xr_vk_copy_d3d_declaration",
        "declaration->GetDeclaration",
        "xr_vk_resolve_shader_pipeline",
        "u64 render_state_identity;",
        "a.render_state_identity == b.render_state_identity",
        "const xr_vk_render_state_snapshot* render_state",
        "!render_state || !render_state->identity",
        "key.render_state_identity = render_state->identity",
        "key.render_pass_generation = g_render_pass_generation",
        "xr_vk_build_vertex_input_layout",
        "xr_vk_d3d_primitive_to_topology",
        "&vertex_layout, topology, render_state)",
        "xrRender_vk_register_shader_spirv",
        "words[0] != 0x07230203u",
        "xr_vk_clear_shader_pipeline_cache();",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan shader pipeline cache validation failed: missing {token}")

    print("[vulkan-shader-pipeline-cache] legacy name registry isolated behind canonical render-state-aware pipeline identity")


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep the legacy name-based Vulkan shader registry fail-closed and canonical render-state aware.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
