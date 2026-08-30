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
// The active D3D9 VS/PS handles are part of the ABI so xrRender_VK can map the exact
// shader pair to a Vulkan pipeline instead of guessing from geometry alone.
typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,
    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
    IDirect3DIndexBuffer9* index_buffer, IDirect3DVertexShader9* vertex_shader,
    IDirect3DPixelShader9* pixel_shader, u32 base_vertex, u32 start_vertex, u32 vertex_count,
    u32 start_index, u32 primitive_count);
typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,
    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,
    u32 start_vertex, u32 primitive_count);

extern ENGINE_API xr_vk_backend_draw_indexed_fn g_xr_vk_backend_draw_indexed;
extern ENGINE_API xr_vk_backend_draw_fn g_xr_vk_backend_draw;
'''
    if "g_xr_vk_backend_draw_indexed" not in h:
        if marker not in h:
            raise RuntimeError("backend dispatch: R_Backend.h include marker not found")
        h = h.replace(marker, marker + contract, 1)
        backend_h.write_text(h, encoding="utf-8")
    elif "IDirect3DVertexShader9* vertex_shader" not in h:
        old_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count);'''
        new_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, IDirect3DVertexShader9* vertex_shader,\n    IDirect3DPixelShader9* pixel_shader, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count);'''
        old_plain = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    u32 start_vertex, u32 primitive_count);'''
        new_plain = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 start_vertex, u32 primitive_count);'''
        if old_indexed not in h or old_plain not in h:
            raise RuntimeError("backend dispatch: existing ABI marker not found for shader-aware upgrade")
        h = h.replace(old_indexed, new_indexed, 1).replace(old_plain, new_plain, 1)
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
    indexed_new = '''\tconstants.flush();\n\tif (g_xr_vk_backend_draw_indexed &&\n\t\tg_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV, startV, countV, startI, PC))\n\t{\n\t\tPGO(Msg("PGO:VK_DIP:%dv/%df", countV, PC));\n\t\treturn;\n\t}\n\tCHK_DX(HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC));\n'''
    indexed_legacy_dispatch = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV, startV, countV, startI, PC)"
    indexed_shader_dispatch = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV, startV, countV, startI, PC)"
    if indexed_legacy_dispatch in rt:
        rt = rt.replace(indexed_legacy_dispatch, indexed_shader_dispatch, 1)
    elif "PGO:VK_DIP" not in rt:
        if indexed_old not in rt:
            raise RuntimeError("backend dispatch: indexed Render marker not found")
        rt = rt.replace(indexed_old, indexed_new, 1)

    draw_old = '''\tconstants.flush();\n\tCHK_DX(HW.pDevice->DrawPrimitive(T, startV, PC));\n'''
    draw_new = '''\tconstants.flush();\n\tif (g_xr_vk_backend_draw && g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV, PC))\n\t{\n\t\tPGO(Msg("PGO:VK_DP:%dv/%df", 3 * PC, PC));\n\t\treturn;\n\t}\n\tCHK_DX(HW.pDevice->DrawPrimitive(T, startV, PC));\n'''
    plain_legacy_dispatch = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV, PC)"
    plain_shader_dispatch = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV, PC)"
    if plain_legacy_dispatch in rt:
        rt = rt.replace(plain_legacy_dispatch, plain_shader_dispatch, 1)
    elif "PGO:VK_DP" not in rt:
        if draw_old not in rt:
            raise RuntimeError("backend dispatch: non-indexed Render marker not found")
        rt = rt.replace(draw_old, draw_new, 1)
    backend_runtime.write_text(rt, encoding="utf-8")

    api = engine_api.read_text(encoding="utf-8")
    resolve = '''\tif (hRender)\n\t{\n\t\tg_xr_vk_backend_draw_indexed = reinterpret_cast<xr_vk_backend_draw_indexed_fn>(\n\t\t\tGetProcAddress(hRender, "xrRender_vk_backend_draw_indexed"));\n\t\tg_xr_vk_backend_draw = reinterpret_cast<xr_vk_backend_draw_fn>(\n\t\t\tGetProcAddress(hRender, "xrRender_vk_backend_draw"));\n\t}\n\n'''
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
// Shader handles are mandatory because a Vulkan pipeline is keyed by the exact VS/PS pair
// plus declaration/topology/render-pass generation.
extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed(
    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,
    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,
    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,
    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)
{
    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||
        !vertex_shader || !pixel_shader || !vertex_stride || !vertex_count || !primitive_count)
        return FALSE;
    // The next bridge stage associates D3D shader/resource identities with SPIR-V modules,
    // mirrored buffers and a render-pass-generation-safe VkPipeline.
    return FALSE;
}

extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(
    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,
    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,
    u32 start_vertex, u32 primitive_count)
{
    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer ||
        !vertex_shader || !pixel_shader || !vertex_stride || !primitive_count)
        return FALSE;
    return FALSE;
}
'''
    if "xrRender_vk_backend_draw_indexed" not in vk:
        vk += exports
    elif "IDirect3DVertexShader9* vertex_shader" not in vk[vk.find("xrRender_vk_backend_draw_indexed"):]:
        old_indexed_sig = '''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed(\n    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)'''
        new_indexed_sig = '''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed(\n    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)'''
        old_plain_sig = '''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(\n    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, u32 start_vertex, u32 primitive_count)'''
        new_plain_sig = '''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(\n    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 start_vertex, u32 primitive_count)'''
        if old_indexed_sig not in vk or old_plain_sig not in vk:
            raise RuntimeError("backend dispatch: renderer export ABI marker not found for shader-aware upgrade")
        vk = vk.replace(old_indexed_sig, new_indexed_sig, 1).replace(old_plain_sig, new_plain_sig, 1)
        indexed_guard_old = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_stride || !vertex_count || !primitive_count)'''
        indexed_guard_new = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_stride || !vertex_count || !primitive_count)'''
        plain_guard_old = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !vertex_stride || !primitive_count)'''
        plain_guard_new = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_stride || !primitive_count)'''
        if indexed_guard_old not in vk or plain_guard_old not in vk:
            raise RuntimeError("backend dispatch: renderer fail-closed guard marker not found for shader-aware upgrade")
        vk = vk.replace(indexed_guard_old, indexed_guard_new, 1).replace(plain_guard_old, plain_guard_new, 1)
    vk_source.write_text(vk, encoding="utf-8")

    required = {
        backend_h: ("xr_vk_backend_draw_indexed_fn", "IDirect3DVertexShader9* vertex_shader", "IDirect3DPixelShader9* pixel_shader", "g_xr_vk_backend_draw"),
        backend_runtime: ("g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps", "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps", "DrawIndexedPrimitive", "DrawPrimitive"),
        engine_api: ("GetProcAddress(hRender, \"xrRender_vk_backend_draw_indexed\")", "GetProcAddress(hRender, \"xrRender_vk_backend_draw\")"),
        vk_source: ("__declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed", "IDirect3DVertexShader9* vertex_shader", "!vertex_shader || !pixel_shader", "return FALSE;"),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"backend dispatch validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-dispatch] shader-aware production CBackend draw dispatch + fail-closed D3D fallback installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect SHOC CBackend::Render to renderer-DLL Vulkan draw dispatch with shader-aware safe D3D fallback.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_backend_dispatch(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
