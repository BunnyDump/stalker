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

    struct xr_vk_backend_pipeline_key
    {
        u64 vertex_shader_identity;
        u64 pixel_shader_identity;
        u64 vertex_declaration_identity;
        u32 vertex_stride;
        VkPrimitiveTopology topology;
        u64 render_pass_generation;
    };

    struct xr_vk_backend_pipeline_record
    {
        xr_vk_backend_pipeline_key key;
        VkPipeline pipeline;
    };

    xr_vector<xr_vk_backend_pipeline_record> g_backend_pipelines;
'''
    if "struct xr_vk_backend_pipeline_key" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan backend pipeline registry: graphics-pipeline state marker not found")
        text = text.replace(state_marker, state_block, 1)

    helper_marker = "    u64 xr_vk_hash_shader_bytecode(const void* data, u32 size)\n"
    helpers = r'''    bool xr_vk_vertex_declaration_identity(IDirect3DVertexDeclaration9* declaration,
        u64& identity, xr_vk_vertex_input_layout& layout, u32 vertex_stride)
    {
        identity = 0;
        if (!declaration || !vertex_stride)
            return false;

        UINT count = 0;
        if (FAILED(declaration->GetDeclaration(NULL, &count)) || !count || count > MAX_FVF_DECL_SIZE)
            return false;
        xr_vector<D3DVERTEXELEMENT9> elements(count);
        UINT actual_count = count;
        if (FAILED(declaration->GetDeclaration(&elements[0], &actual_count)) || !actual_count || actual_count > count)
            return false;
        if (!xr_vk_build_vertex_input_layout(&elements[0], actual_count, vertex_stride, layout))
            return false;

        u64 hash = 1469598103934665603ull;
        for (UINT i = 0; i < actual_count; ++i)
        {
            const D3DVERTEXELEMENT9& element = elements[i];
            const u32 fields[] = {
                static_cast<u32>(element.Stream), static_cast<u32>(element.Offset),
                static_cast<u32>(element.Type), static_cast<u32>(element.Method),
                static_cast<u32>(element.Usage), static_cast<u32>(element.UsageIndex)
            };
            for (u32 field = 0; field < sizeof(fields) / sizeof(fields[0]); ++field)
            {
                u32 value = fields[field];
                for (u32 byte_index = 0; byte_index < sizeof(value); ++byte_index)
                {
                    hash ^= static_cast<u64>(value & 0xffu);
                    hash *= 1099511628211ull;
                    value >>= 8;
                }
            }
        }
        identity = hash ? hash : 1ull;
        return true;
    }

    bool xr_vk_backend_pipeline_key_equal(const xr_vk_backend_pipeline_key& a,
        const xr_vk_backend_pipeline_key& b)
    {
        return a.vertex_shader_identity == b.vertex_shader_identity &&
            a.pixel_shader_identity == b.pixel_shader_identity &&
            a.vertex_declaration_identity == b.vertex_declaration_identity &&
            a.vertex_stride == b.vertex_stride && a.topology == b.topology &&
            a.render_pass_generation == b.render_pass_generation;
    }

    bool xr_vk_make_backend_pipeline_key(u64 vertex_shader_identity, u64 pixel_shader_identity,
        IDirect3DVertexDeclaration9* declaration, u32 vertex_stride, D3DPRIMITIVETYPE primitive,
        xr_vk_backend_pipeline_key& key, xr_vk_vertex_input_layout& layout)
    {
        if (!vertex_shader_identity || !pixel_shader_identity || !declaration || !vertex_stride)
            return false;

        VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_MAX_ENUM;
        if (!xr_vk_d3d_primitive_to_topology(primitive, topology))
            return false;

        u64 declaration_identity = 0;
        if (!xr_vk_vertex_declaration_identity(declaration, declaration_identity, layout, vertex_stride))
            return false;

        key.vertex_shader_identity = vertex_shader_identity;
        key.pixel_shader_identity = pixel_shader_identity;
        key.vertex_declaration_identity = declaration_identity;
        key.vertex_stride = vertex_stride;
        key.topology = topology;
        key.render_pass_generation = g_render_pass_generation;
        return key.render_pass_generation != 0;
    }

    VkPipeline xr_vk_find_backend_pipeline(const xr_vk_backend_pipeline_key& key)
    {
        for (u32 i = 0; i < g_backend_pipelines.size(); ++i)
        {
            const xr_vk_backend_pipeline_record& record = g_backend_pipelines[i];
            if (!xr_vk_backend_pipeline_key_equal(record.key, key))
                continue;
            if (!xr_vk_pipeline_is_current(record.pipeline))
                return VK_NULL_HANDLE;
            return record.pipeline;
        }
        return VK_NULL_HANDLE;
    }

    bool xr_vk_register_backend_pipeline(const xr_vk_backend_pipeline_key& key, VkPipeline pipeline)
    {
        if (pipeline == VK_NULL_HANDLE || !xr_vk_pipeline_is_current(pipeline) ||
            key.render_pass_generation != g_render_pass_generation)
            return false;
        for (u32 i = 0; i < g_backend_pipelines.size(); ++i)
        {
            if (!xr_vk_backend_pipeline_key_equal(g_backend_pipelines[i].key, key))
                continue;
            g_backend_pipelines[i].pipeline = pipeline;
            return true;
        }
        xr_vk_backend_pipeline_record record;
        record.key = key;
        record.pipeline = pipeline;
        g_backend_pipelines.push_back(record);
        return true;
    }

    void xr_vk_prune_backend_pipelines()
    {
        for (u32 i = 0; i < g_backend_pipelines.size();)
        {
            if (g_backend_pipelines[i].key.render_pass_generation == g_render_pass_generation &&
                xr_vk_pipeline_is_current(g_backend_pipelines[i].pipeline))
            {
                ++i;
                continue;
            }
            g_backend_pipelines.erase(g_backend_pipelines.begin() + i);
        }
    }

'''
    if "xr_vk_make_backend_pipeline_key" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan backend pipeline registry: shader identity helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan backend pipeline registry: renderer exports not found")

    indexed = text[indexed_start:plain_start]
    identity_guard = '''    if (!xr_vk_vertex_shader_bytecode_identity(vertex_shader, vertex_shader_identity) ||
        !xr_vk_pixel_shader_bytecode_identity(pixel_shader, pixel_shader_identity))
        return FALSE;'''
    lookup = r'''

    xr_vk_backend_pipeline_key pipeline_key = {};
    xr_vk_vertex_input_layout vertex_layout = {};
    if (!xr_vk_make_backend_pipeline_key(vertex_shader_identity, pixel_shader_identity,
        declaration, vertex_stride, primitive, pipeline_key, vertex_layout))
        return FALSE;
    xr_vk_prune_backend_pipelines();
    VkPipeline pipeline = xr_vk_find_backend_pipeline(pipeline_key);
    if (pipeline == VK_NULL_HANDLE)
        return FALSE;'''
    if "xr_vk_make_backend_pipeline_key" not in indexed:
        if identity_guard not in indexed:
            raise RuntimeError("Vulkan backend pipeline registry: indexed shader identity guard not found")
        indexed = indexed.replace(identity_guard, identity_guard + lookup, 1)
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = text[plain_start:]
    if "xr_vk_make_backend_pipeline_key" not in plain:
        if identity_guard not in plain:
            raise RuntimeError("Vulkan backend pipeline registry: plain shader identity guard not found")
        plain = plain.replace(identity_guard, identity_guard + lookup, 1)
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_backend_pipeline_key",
        "u64 vertex_shader_identity;", "u64 pixel_shader_identity;",
        "u64 vertex_declaration_identity;", "u32 vertex_stride;",
        "VkPrimitiveTopology topology;", "u64 render_pass_generation;",
        "declaration->GetDeclaration(NULL, &count)",
        "xr_vk_build_vertex_input_layout(&elements[0], actual_count, vertex_stride, layout)",
        "xr_vk_backend_pipeline_key_equal",
        "xr_vk_make_backend_pipeline_key",
        "key.render_pass_generation = g_render_pass_generation;",
        "xr_vk_find_backend_pipeline",
        "xr_vk_register_backend_pipeline",
        "xr_vk_prune_backend_pipelines",
        "xr_vk_pipeline_is_current(record.pipeline)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend pipeline registry validation failed: missing {token}")

    indexed_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    for label, block in (("indexed", final[indexed_start:plain_start]), ("plain", final[plain_start:])):
        for token in (
            "xr_vk_backend_pipeline_key pipeline_key = {};",
            "xr_vk_vertex_input_layout vertex_layout = {};",
            "xr_vk_make_backend_pipeline_key(vertex_shader_identity, pixel_shader_identity",
            "xr_vk_find_backend_pipeline(pipeline_key)",
            "if (pipeline == VK_NULL_HANDLE)",
        ):
            if token not in block:
                raise RuntimeError(f"Vulkan backend pipeline registry validation failed in {label} export: missing {token}")
        identity = block.find("xr_vk_vertex_shader_bytecode_identity")
        key = block.find("xr_vk_make_backend_pipeline_key")
        lookup_pos = block.find("xr_vk_find_backend_pipeline")
        fallback = block.rfind("return FALSE;")
        if min(identity, key, lookup_pos, fallback) < 0 or not identity < key < lookup_pos < fallback:
            raise RuntimeError(f"Vulkan backend pipeline registry validation failed in {label} export: lookup order invalid")

    print("[vulkan-backend-pipeline] bytecode/declaration/stride/topology/render-pass generation keyed fail-closed registry installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a fail-closed Vulkan backend pipeline registry keyed by stable SHOC draw state.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
