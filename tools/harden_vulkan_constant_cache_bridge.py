from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    cache_h = root / "xr_3da" / "r_constants_cache.h"
    cache_cpp = root / "xr_3da" / "r_constants_cache.cpp"
    engine_api = root / "xr_3da" / "EngineAPI.cpp"
    vk_cpp = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (cache_h, cache_cpp, engine_api, vk_cpp):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = cache_h.read_text(encoding="utf-8")
    pragma = "#pragma once\n"
    abi = r'''

// Mirrors the exact float4 register ranges committed by the D3D9 constant cache.
// stage: 0 = pixel, 1 = vertex. No STL/ref_* types cross the renderer DLL ABI.
typedef BOOL(__cdecl* xr_vk_constant_range_upload_fn)(u32 stage, u32 first_register,
    u32 register_count, const Fvector4* values);
extern ENGINE_API xr_vk_constant_range_upload_fn g_xr_vk_constant_range_upload;
'''
    if "g_xr_vk_constant_range_upload" not in h:
        if pragma not in h:
            raise RuntimeError("Vulkan constant bridge: pragma marker missing")
        h = h.replace(pragma, pragma + abi, 1)
        cache_h.write_text(h, encoding="utf-8")

    cpp = cache_cpp.read_text(encoding="utf-8")
    include_marker = '#include "r_constants_cache.h"\n'
    if "g_xr_vk_constant_range_upload = NULL" not in cpp:
        if include_marker not in cpp:
            raise RuntimeError("Vulkan constant bridge: cache include marker missing")
        cpp = cpp.replace(include_marker, include_marker + "\nENGINE_API xr_vk_constant_range_upload_fn g_xr_vk_constant_range_upload = NULL;\n", 1)

    ps_call = 'CHK_DX(HW.pDevice->SetPixelShaderConstantF(F.r_lo(), (float*)F.access(F.r_lo()), count));'
    ps_new = '''if (g_xr_vk_constant_range_upload)
                        g_xr_vk_constant_range_upload(0, F.r_lo(), count, F.access(F.r_lo()));
                    CHK_DX(HW.pDevice->SetPixelShaderConstantF(F.r_lo(), (float*)F.access(F.r_lo()), count));'''
    if "g_xr_vk_constant_range_upload(0, F.r_lo()" not in cpp:
        if ps_call not in cpp:
            raise RuntimeError("Vulkan constant bridge: pixel flush marker missing")
        cpp = cpp.replace(ps_call, ps_new, 1)

    vs_call = 'CHK_DX(HW.pDevice->SetVertexShaderConstantF(F.r_lo(), (float*)F.access(F.r_lo()), count));'
    vs_new = '''if (g_xr_vk_constant_range_upload)
                    g_xr_vk_constant_range_upload(1, F.r_lo(), count, F.access(F.r_lo()));
                CHK_DX(HW.pDevice->SetVertexShaderConstantF(F.r_lo(), (float*)F.access(F.r_lo()), count));'''
    if "g_xr_vk_constant_range_upload(1, F.r_lo()" not in cpp:
        if vs_call not in cpp:
            raise RuntimeError("Vulkan constant bridge: vertex flush marker missing")
        cpp = cpp.replace(vs_call, vs_new, 1)
    cache_cpp.write_text(cpp, encoding="utf-8")

    api = engine_api.read_text(encoding="utf-8")
    resolve_anchor = '''\t\tg_xr_vk_index_stream_upload = reinterpret_cast<xr_vk_index_stream_upload_fn>(
\t\t\tGetProcAddress(hRender, "xrRender_vk_index_stream_upload"));
'''
    resolve_block = resolve_anchor + '''\t\tg_xr_vk_constant_range_upload = reinterpret_cast<xr_vk_constant_range_upload_fn>(
\t\t\tGetProcAddress(hRender, "xrRender_vk_constant_range_upload"));
'''
    if "xrRender_vk_constant_range_upload" not in api:
        if resolve_anchor not in api:
            raise RuntimeError("Vulkan constant bridge: EngineAPI resolve anchor missing")
        api = api.replace(resolve_anchor, resolve_block, 1)

    unload_anchor = "\t\tg_xr_vk_index_stream_upload = NULL;\n"
    if "\t\tg_xr_vk_constant_range_upload = NULL;\n" not in api:
        if unload_anchor not in api:
            raise RuntimeError("Vulkan constant bridge: EngineAPI unload anchor missing")
        api = api.replace(unload_anchor, unload_anchor + "\t\tg_xr_vk_constant_range_upload = NULL;\n", 1)
    engine_api.write_text(api, encoding="utf-8")

    vk = vk_cpp.read_text(encoding="utf-8")
    state_anchor = "    VkDeviceSize g_uniform_stream_capacity = 0;\n"
    state = state_anchor + '''    Fvector4 g_backend_ps_constants[256];
    Fvector4 g_backend_vs_constants[256];
    u32 g_backend_ps_constant_lo = 256;
    u32 g_backend_ps_constant_hi = 0;
    u32 g_backend_vs_constant_lo = 256;
    u32 g_backend_vs_constant_hi = 0;
    u64 g_backend_constant_generation = 0;
'''
    if "g_backend_ps_constants[256]" not in vk:
        if state_anchor not in vk:
            raise RuntimeError("Vulkan constant bridge: uniform stream state anchor missing")
        vk = vk.replace(state_anchor, state, 1)

    export_anchor = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_vertex_stream_upload('
    export = r'''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_constant_range_upload(
    u32 stage, u32 first_register, u32 register_count, const Fvector4* values)
{
    if (!values || !register_count || first_register >= 256 || register_count > 256 - first_register)
        return FALSE;

    Fvector4* destination = NULL;
    u32* lo = NULL;
    u32* hi = NULL;
    if (stage == 0)
    {
        destination = g_backend_ps_constants;
        lo = &g_backend_ps_constant_lo;
        hi = &g_backend_ps_constant_hi;
    }
    else if (stage == 1)
    {
        destination = g_backend_vs_constants;
        lo = &g_backend_vs_constant_lo;
        hi = &g_backend_vs_constant_hi;
    }
    else
        return FALSE;

    CopyMemory(destination + first_register, values, register_count * sizeof(Fvector4));
    if (*lo > first_register) *lo = first_register;
    const u32 end = first_register + register_count;
    if (*hi < end) *hi = end;
    ++g_backend_constant_generation;
    if (!g_backend_constant_generation) ++g_backend_constant_generation;
    return TRUE;
}

'''
    if "xrRender_vk_constant_range_upload" not in vk:
        pos = vk.find(export_anchor)
        if pos < 0:
            raise RuntimeError("Vulkan constant bridge: stream export anchor missing")
        vk = vk[:pos] + export + vk[pos:]

    # Do not claim per-draw readiness yet. This helper only establishes a bounded,
    # generation-tracked CPU snapshot; descriptor/uniform packing is the next layer.
    vk_cpp.write_text(vk, encoding="utf-8")

    final_h = cache_h.read_text(encoding="utf-8")
    final_cpp = cache_cpp.read_text(encoding="utf-8")
    final_api = engine_api.read_text(encoding="utf-8")
    final_vk = vk_cpp.read_text(encoding="utf-8")
    required = (
        (final_h, "xr_vk_constant_range_upload_fn"),
        (final_cpp, "g_xr_vk_constant_range_upload(0, F.r_lo(), count"),
        (final_cpp, "g_xr_vk_constant_range_upload(1, F.r_lo(), count"),
        (final_api, 'GetProcAddress(hRender, "xrRender_vk_constant_range_upload")'),
        (final_vk, "g_backend_ps_constants[256]"),
        (final_vk, "g_backend_vs_constants[256]"),
        (final_vk, "xrRender_vk_constant_range_upload"),
        (final_vk, "register_count > 256 - first_register"),
        (final_vk, "g_backend_constant_generation"),
    )
    for haystack, token in required:
        if token not in haystack:
            raise RuntimeError(f"Vulkan constant bridge validation failed: missing {token}")

    print("[vulkan-constant-cache] exact D3D9 PS/VS float4 flush ranges mirrored through bounded C ABI")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror SHOC D3D9 shader constant flush ranges for the Vulkan backend.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
