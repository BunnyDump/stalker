from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    helper_marker = "    bool xr_vk_vertex_declaration_identity(IDirect3DVertexDeclaration9* declaration,\n"
    helpers = r'''    bool xr_vk_read_spirv_sidecar(const char* path, xr_vector<u8>& bytes)
    {
        bytes.clear();
        if (!path || !path[0])
            return false;
        HANDLE file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
        if (file == INVALID_HANDLE_VALUE)
            return false;

        LARGE_INTEGER size = {};
        const bool size_ok = GetFileSizeEx(file, &size) != FALSE && size.QuadPart >= 20 &&
            size.QuadPart <= 16ll * 1024ll * 1024ll && (size.QuadPart & 3ll) == 0;
        if (!size_ok)
        {
            CloseHandle(file);
            return false;
        }

        bytes.resize(static_cast<u32>(size.QuadPart));
        DWORD read = 0;
        const BOOL read_ok = ReadFile(file, &bytes[0], static_cast<DWORD>(bytes.size()), &read, NULL);
        CloseHandle(file);
        if (!read_ok || read != bytes.size())
        {
            bytes.clear();
            return false;
        }

        const u32* words = reinterpret_cast<const u32*>(&bytes[0]);
        if (words[0] != 0x07230203u)
        {
            bytes.clear();
            return false;
        }
        return true;
    }

    bool xr_vk_build_shader_sidecar_path(char* path, size_t capacity, const char* stage, u64 identity)
    {
        if (!path || capacity < 64 || !stage || !stage[0] || !identity)
            return false;
        const int written = _snprintf_s(path, capacity, _TRUNCATE,
            "gamedata\\shaders\\vulkan\\cache\\%s_%016I64x.spv",
            stage, static_cast<unsigned __int64>(identity));
        return written > 0 && static_cast<size_t>(written) < capacity;
    }

    VkPipeline xr_vk_materialize_backend_pipeline(const xr_vk_backend_pipeline_key& key,
        const xr_vk_vertex_input_layout& vertex_layout)
    {
        if (!key.vertex_shader_identity || !key.pixel_shader_identity ||
            key.render_pass_generation != g_render_pass_generation ||
            key.topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM)
            return VK_NULL_HANDLE;

        char vertex_path[MAX_PATH] = {};
        char pixel_path[MAX_PATH] = {};
        if (!xr_vk_build_shader_sidecar_path(vertex_path, sizeof(vertex_path), "vs", key.vertex_shader_identity) ||
            !xr_vk_build_shader_sidecar_path(pixel_path, sizeof(pixel_path), "ps", key.pixel_shader_identity))
            return VK_NULL_HANDLE;

        xr_vector<u8> vertex_spirv;
        xr_vector<u8> pixel_spirv;
        if (!xr_vk_read_spirv_sidecar(vertex_path, vertex_spirv) ||
            !xr_vk_read_spirv_sidecar(pixel_path, pixel_spirv))
            return VK_NULL_HANDLE;

        VkPipeline pipeline = xr_vk_create_graphics_pipeline(
            &vertex_spirv[0], vertex_spirv.size(), "main",
            &pixel_spirv[0], pixel_spirv.size(), "main",
            &vertex_layout, key.topology);
        if (pipeline == VK_NULL_HANDLE)
            return VK_NULL_HANDLE;
        if (!xr_vk_register_backend_pipeline(key, pipeline))
        {
            xr_vk_destroy_pipeline_handle(pipeline);
            return VK_NULL_HANDLE;
        }
        return pipeline;
    }

'''
    if "xr_vk_materialize_backend_pipeline" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan SPIR-V sidecar loader: pipeline registry helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    miss = '''    VkPipeline pipeline = xr_vk_find_backend_pipeline(pipeline_key);
    if (pipeline == VK_NULL_HANDLE)
        return FALSE;'''
    replacement = '''    VkPipeline pipeline = xr_vk_find_backend_pipeline(pipeline_key);
    if (pipeline == VK_NULL_HANDLE)
        pipeline = xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout);
    if (pipeline == VK_NULL_HANDLE)
        return FALSE;'''

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan SPIR-V sidecar loader: backend exports not found")

    indexed = text[indexed_start:plain_start]
    if "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)" not in indexed:
        if miss not in indexed:
            raise RuntimeError("Vulkan SPIR-V sidecar loader: indexed pipeline miss marker not found")
        indexed = indexed.replace(miss, replacement, 1)
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = text[plain_start:]
    if "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)" not in plain:
        if miss not in plain:
            raise RuntimeError("Vulkan SPIR-V sidecar loader: non-indexed pipeline miss marker not found")
        plain = plain.replace(miss, replacement, 1)
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "xr_vk_read_spirv_sidecar",
        "CreateFileA(path, GENERIC_READ, FILE_SHARE_READ",
        "size.QuadPart <= 16ll * 1024ll * 1024ll",
        "words[0] != 0x07230203u",
        "gamedata\\\\shaders\\\\vulkan\\\\cache\\\\%s_%016I64x.spv",
        "xr_vk_materialize_backend_pipeline",
        '"vs", key.vertex_shader_identity',
        '"ps", key.pixel_shader_identity',
        '"main"',
        "xr_vk_register_backend_pipeline(key, pipeline)",
        "xr_vk_destroy_pipeline_handle(pipeline)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan SPIR-V sidecar loader validation failed: missing {token}")

    indexed_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    for label, block in (("indexed", final[indexed_start:plain_start]), ("plain", final[plain_start:])):
        lookup = block.find("xr_vk_find_backend_pipeline(pipeline_key)")
        materialize = block.find("xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)")
        fallback = block.find("if (pipeline == VK_NULL_HANDLE)", materialize)
        if min(lookup, materialize, fallback) < 0 or not lookup < materialize < fallback:
            raise RuntimeError(f"Vulkan SPIR-V sidecar loader validation failed in {label}: fail-closed lookup/materialize order invalid")

    print("[vulkan-spv-sidecar] bytecode-hash keyed VS/PS SPIR-V loading + validated pipeline materialization installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install deterministic SPIR-V sidecar loading for SHOC Vulkan backend pipelines.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
