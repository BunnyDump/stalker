from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    helper_marker = "    VkPipeline xr_vk_find_backend_pipeline(const xr_vk_backend_pipeline_key& key)\n"
    helpers = r'''    bool xr_vk_read_spirv_file(const char* path, xr_vector<u8>& bytes)
    {
        bytes.clear();
        if (!path || !path[0])
            return false;
        HANDLE file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
        if (file == INVALID_HANDLE_VALUE)
            return false;
        LARGE_INTEGER size = {};
        const bool valid_size = GetFileSizeEx(file, &size) != FALSE && size.QuadPart >= 20 &&
            size.QuadPart <= (16ll * 1024ll * 1024ll) && (size.QuadPart & 3ll) == 0;
        if (!valid_size)
        {
            CloseHandle(file);
            return false;
        }
        bytes.resize(static_cast<u32>(size.QuadPart));
        DWORD read = 0;
        const BOOL ok = ReadFile(file, &bytes[0], static_cast<DWORD>(bytes.size()), &read, NULL);
        CloseHandle(file);
        if (!ok || read != bytes.size())
        {
            bytes.clear();
            return false;
        }
        const u32 magic = *reinterpret_cast<const u32*>(&bytes[0]);
        if (magic != 0x07230203u)
        {
            bytes.clear();
            return false;
        }
        return true;
    }

    bool xr_vk_load_shader_sidecar(const char* stage, u64 identity, xr_vector<u8>& bytes)
    {
        if (!stage || !stage[0] || !identity)
            return false;

        char filename[96] = {};
        sprintf_s(filename, sizeof(filename), "%s_%016llx.spv", stage,
            static_cast<unsigned long long>(identity));

        char relative_path[MAX_PATH] = {};
        sprintf_s(relative_path, sizeof(relative_path), "gamedata\\shaders\\r2\\vk_spv\\%s", filename);
        if (xr_vk_read_spirv_file(relative_path, bytes))
            return true;

        char module_path[MAX_PATH] = {};
        const DWORD length = GetModuleFileNameA(NULL, module_path, MAX_PATH);
        if (!length || length >= MAX_PATH)
            return false;
        char* slash = strrchr(module_path, '\\');
        if (!slash)
            slash = strrchr(module_path, '/');
        if (!slash)
            return false;
        *slash = 0;

        char sibling_path[MAX_PATH] = {};
        sprintf_s(sibling_path, sizeof(sibling_path),
            "%s\\..\\gamedata\\shaders\\r2\\vk_spv\\%s", module_path, filename);
        return xr_vk_read_spirv_file(sibling_path, bytes);
    }

    VkPipeline xr_vk_materialize_backend_pipeline(const xr_vk_backend_pipeline_key& key,
        const xr_vk_vertex_input_layout& vertex_layout)
    {
        // Sidecars are keyed by the stable D3D9 bytecode identities captured from the live shader objects.
        // They must be compiled offline from the exact matching SHOC shader variant and use entry point "main".
        xr_vector<u8> vs_spirv;
        xr_vector<u8> ps_spirv;
        if (!xr_vk_load_shader_sidecar("vs", key.vertex_shader_identity, vs_spirv) ||
            !xr_vk_load_shader_sidecar("ps", key.pixel_shader_identity, ps_spirv))
            return VK_NULL_HANDLE;

        VkPipeline pipeline = xr_vk_create_graphics_pipeline(&vs_spirv[0], vs_spirv.size(), "main",
            &ps_spirv[0], ps_spirv.size(), "main", &vertex_layout, key.topology);
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
            raise RuntimeError("Vulkan SPIR-V sidecar: backend pipeline lookup marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan SPIR-V sidecar: backend exports not found")

    miss = '''    VkPipeline pipeline = xr_vk_find_backend_pipeline(pipeline_key);
    if (pipeline == VK_NULL_HANDLE)
        return FALSE;'''
    replacement = '''    VkPipeline pipeline = xr_vk_find_backend_pipeline(pipeline_key);
    if (pipeline == VK_NULL_HANDLE)
    {
        // Pipeline state translation is not complete yet. Keep production fail-closed until the
        // D3D9 raster/depth/blend state bridge explicitly marks this draw state compatible.
        const bool pipeline_state_compatible = false;
        if (!pipeline_state_compatible)
            return FALSE;
        pipeline = xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout);
        if (pipeline == VK_NULL_HANDLE)
            return FALSE;
    }'''

    indexed = text[indexed_start:plain_start]
    if "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)" not in indexed:
        if miss not in indexed:
            raise RuntimeError("Vulkan SPIR-V sidecar: indexed pipeline miss marker not found")
        indexed = indexed.replace(miss, replacement, 1)
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = text[plain_start:]
    if "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)" not in plain:
        if miss not in plain:
            raise RuntimeError("Vulkan SPIR-V sidecar: plain pipeline miss marker not found")
        plain = plain.replace(miss, replacement, 1)
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "bool xr_vk_read_spirv_file", "CreateFileA", "GetFileSizeEx", "ReadFile",
        "0x07230203u", "bool xr_vk_load_shader_sidecar", "vs_%", "vk_spv",
        "GetModuleFileNameA", "VkPipeline xr_vk_materialize_backend_pipeline",
        "xr_vk_create_graphics_pipeline(&vs_spirv[0]", "xr_vk_register_backend_pipeline(key, pipeline)",
        "xr_vk_destroy_pipeline_handle(pipeline)", "const bool pipeline_state_compatible = false;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan SPIR-V sidecar validation failed: missing {token}")

    for label, start, end in (
        ("indexed", final.find('xrRender_vk_backend_draw_indexed'), final.find('xrRender_vk_backend_draw(', final.find('xrRender_vk_backend_draw_indexed'))),
        ("plain", final.find('xrRender_vk_backend_draw(', final.find('xrRender_vk_backend_draw_indexed')), len(final)),
    ):
        block = final[start:end]
        gate = block.find("pipeline_state_compatible = false")
        materialize = block.find("xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)")
        if gate < 0 or materialize < 0 or gate > materialize:
            raise RuntimeError(f"Vulkan SPIR-V sidecar validation failed in {label}: fail-closed state gate missing")

    print("[vulkan-shader-sidecar] bytecode-identity SPIR-V loader/materializer installed behind fail-closed render-state gate")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install fail-closed SPIR-V sidecar loading for live SHOC Vulkan backend pipelines.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
