from __future__ import annotations

import argparse
from pathlib import Path


def install_backend_dispatch(root: Path) -> None:
    root = root.resolve()
    backend_h = root / "xr_3da" / "R_Backend.h"
    backend_cpp = root / "xr_3da" / "R_Backend.cpp"
    backend_runtime = root / "xr_3da" / "R_Backend_Runtime.h"
    engine_api = root / "xr_3da" / "EngineAPI.cpp"
    vk_source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (backend_h, backend_cpp, backend_runtime, engine_api, vk_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = backend_h.read_text(encoding="utf-8")
    marker = '#include "fvf.h"\n'
    contract = r'''

// Transitional renderer-DLL dispatch. Returning FALSE keeps the proven D3D9 path alive
// until the Vulkan resource/pipeline association for this draw is complete.
typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,
    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
    IDirect3DIndexBuffer9* index_buffer, u32 base_vertex, u32 start_vertex, u32 vertex_count,
    u32 start_index, u32 primitive_count);
typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,
    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
    u32 start_vertex, u32 primitive_count);

extern ENGINE_API xr_vk_backend_draw_indexed_fn g_xr_vk_backend_draw_indexed;
extern ENGINE_API xr_vk_backend_draw_fn g_xr_vk_backend_draw;
'''
    if "g_xr_vk_backend_draw_indexed" not in h:
        if marker not in h:
            raise RuntimeError("backend dispatch: R_Backend.h include marker not found")
        h = h.replace(marker, marker + contract, 1)
        backend_h.write_text(h, encoding="utf-8")

    cpp = backend_cpp.read_text(encoding="utf-8")
    marker = "ENGINE_API CBackend RCache;\n"
    globals_block = marker + "ENGINE_API xr_vk_backend_draw_indexed_fn g_xr_vk_backend_draw_indexed = NULL;\nENGINE_API xr_vk_backend_draw_fn g_xr_vk_backend_draw = NULL;\n"
    if "g_xr_vk_backend_draw_indexed = NULL" not in cpp:
        if marker not in cpp:
            raise RuntimeError("backend dispatch: R_Backend.cpp RCache marker not found")
        cpp = cpp.replace(marker, globals_block, 1)
        backend_cpp.write_text(cpp, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")
    indexed_old = '''\tconstants.flush();\n\tCHK_DX(HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC));\n'''
    indexed_new = '''\tconstants.flush();\n\tif (g_xr_vk_backend_draw_indexed &&\n\t\tg_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV, startV, countV, startI, PC))\n\t{\n\t\tPGO(Msg("PGO:VK_DIP:%dv/%df", countV, PC));\n\t\treturn;\n\t}\n\tCHK_DX(HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC));\n'''
    if "PGO:VK_DIP" not in rt:
        if indexed_old not in rt:
            raise RuntimeError("backend dispatch: indexed Render marker not found")
        rt = rt.replace(indexed_old, indexed_new, 1)

    draw_old = '''\tconstants.flush();\n\tCHK_DX(HW.pDevice->DrawPrimitive(T, startV, PC));\n'''
    draw_new = '''\tconstants.flush();\n\tif (g_xr_vk_backend_draw && g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV, PC))\n\t{\n\t\tPGO(Msg("PGO:VK_DP:%dv/%df", 3 * PC, PC));\n\t\treturn;\n\t}\n\tCHK_DX(HW.pDevice->DrawPrimitive(T, startV, PC));\n'''
    if "PGO:VK_DP" not in rt:
        if draw_old not in rt:
            raise RuntimeError("backend dispatch: non-indexed Render marker not found")
        rt = rt.replace(draw_old, draw_new, 1)
    backend_runtime.write_text(rt, encoding="utf-8")

    api = engine_api.read_text(encoding="utf-8")
    load_marker = '''\tif (0 == hRender)\n\t{\n\t\t// try to load R1\n'''
    resolve = '''\tif (hRender)\n\t{\n\t\tg_xr_vk_backend_draw_indexed = reinterpret_cast<xr_vk_backend_draw_indexed_fn>(\n\t\t\tGetProcAddress(hRender, "xrRender_vk_backend_draw_indexed"));\n\t\tg_xr_vk_backend_draw = reinterpret_cast<xr_vk_backend_draw_fn>(\n\t\t\tGetProcAddress(hRender, "xrRender_vk_backend_draw"));\n\t}\n\n'''
    # Resolve after final renderer selection, not after the first R2 attempt.
    game_marker = "\n\t// game\n"
    if "xrRender_vk_backend_draw_indexed" not in api:
        if game_marker not in api:
            raise RuntimeError("backend dispatch: EngineAPI game marker not found")
        api = api.replace(game_marker, "\n" + resolve + "\t// game\n", 1)

    destroy_marker = '''\tif (hRender)\n\t{\n\t\tFreeLibrary(hRender);\n'''
    destroy_new = '''\tif (hRender)\n\t{\n\t\tg_xr_vk_backend_draw_indexed = NULL;\n\t\tg_xr_vk_backend_draw = NULL;\n\t\tFreeLibrary(hRender);\n'''
    if "g_xr_vk_backend_draw_indexed = NULL;\n\t\tg_xr_vk_backend_draw = NULL;\n\t\tFreeLibrary" not in api:
        if destroy_marker not in api:
            raise RuntimeError("backend dispatch: EngineAPI renderer destroy marker not found")
        api = api.replace(destroy_marker, destroy_new, 1)
    engine_api.write_text(api, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    exports = r'''

// Production CBackend entry points. Resource/pipeline mapping is deliberately fail-closed:
// FALSE means CBackend executes its original D3D9 draw instead of dropping geometry.
extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed(
    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,
    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,
    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)
{
    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||
        !vertex_stride || !vertex_count || !primitive_count)
        return FALSE;
    // The next bridge stage associates native D3D resources/shaders with their Vulkan mirrors.
    // Never claim a Vulkan draw until that association exists.
    return FALSE;
}

extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(
    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,
    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, u32 start_vertex, u32 primitive_count)
{
    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !vertex_stride || !primitive_count)
        return FALSE;
    return FALSE;
}
'''
    if "xrRender_vk_backend_draw_indexed" not in vk:
        vk += exports
        vk_source.write_text(vk, encoding="utf-8")

    required = {
        backend_h: ("xr_vk_backend_draw_indexed_fn", "g_xr_vk_backend_draw"),
        backend_runtime: ("g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib", "PGO:VK_DP", "DrawIndexedPrimitive", "DrawPrimitive"),
        engine_api: ("GetProcAddress(hRender, \"xrRender_vk_backend_draw_indexed\")", "GetProcAddress(hRender, \"xrRender_vk_backend_draw\")"),
        vk_source: ("__declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed", "return FALSE;"),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"backend dispatch validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-dispatch] production CBackend draw dispatch + fail-closed D3D fallback installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect SHOC CBackend::Render to renderer-DLL Vulkan draw dispatch with safe D3D fallback.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_backend_dispatch(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
