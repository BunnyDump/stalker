from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    backend_h = root / "xr_3da" / "R_Backend.h"
    backend_runtime = root / "xr_3da" / "R_Backend_Runtime.h"
    backend_source = root / "xr_3da" / "R_Backend_Runtime.cpp"
    vk_source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (backend_h, backend_runtime, backend_source, vk_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = backend_h.read_text(encoding="utf-8")

    # Keep stable shader identities in release builds as well. Handles provide a cheap
    # runtime cache key; names provide the bridge to the generated SPIR-V payload.
    state_marker = "\tIDirect3DVertexShader9* vs;\n"
    state_block = state_marker + "\tLPCSTR vk_ps_name;\n\tLPCSTR vk_vs_name;\n"
    if "LPCSTR vk_ps_name;" not in h:
        if state_marker not in h:
            raise RuntimeError("backend shader identity: shader-state marker not found")
        h = h.replace(state_marker, state_block, 1)

    handle_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, IDirect3DVertexShader9* vertex_shader,\n    IDirect3DPixelShader9* pixel_shader, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count);'''
    full_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, IDirect3DVertexShader9* vertex_shader,\n    IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count);'''
    legacy_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count);'''
    if "IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name" not in h:
        if handle_indexed in h:
            h = h.replace(handle_indexed, full_indexed, 1)
        elif legacy_indexed in h:
            legacy_full = full_indexed
            h = h.replace(legacy_indexed, legacy_full, 1)
        else:
            raise RuntimeError("backend shader identity: indexed callback contract marker not found")

    handle_draw = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 start_vertex, u32 primitive_count);'''
    full_draw = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex, u32 primitive_count);'''
    legacy_draw = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    u32 start_vertex, u32 primitive_count);'''
    if "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex" not in h:
        if handle_draw in h:
            h = h.replace(handle_draw, full_draw, 1)
        elif legacy_draw in h:
            h = h.replace(legacy_draw, full_draw, 1)
        else:
            raise RuntimeError("backend shader identity: draw callback contract marker not found")
    backend_h.write_text(h, encoding="utf-8")

    source = backend_source.read_text(encoding="utf-8")
    invalidate_marker = "\tps = NULL;\n\tvs = NULL;\n\tctable = NULL;\n"
    invalidate_new = "\tps = NULL;\n\tvs = NULL;\n\tvk_ps_name = NULL;\n\tvk_vs_name = NULL;\n\tctable = NULL;\n"
    if "\tvk_ps_name = NULL;" not in source:
        if invalidate_marker not in source:
            raise RuntimeError("backend shader identity: Invalidate shader marker not found")
        source = source.replace(invalidate_marker, invalidate_new, 1)
    backend_source.write_text(source, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")

    ps_marker = "\t\tps = _ps;\n\t\tCHK_DX(HW.pDevice->SetPixelShader(ps));\n"
    ps_new = "\t\tps = _ps;\n\t\tvk_ps_name = _n;\n\t\tCHK_DX(HW.pDevice->SetPixelShader(ps));\n"
    if "\t\tvk_ps_name = _n;" not in rt:
        if ps_marker not in rt:
            raise RuntimeError("backend shader identity: set_PS marker not found")
        rt = rt.replace(ps_marker, ps_new, 1)

    vs_marker = "\t\tvs = _vs;\n\t\tCHK_DX(HW.pDevice->SetVertexShader(vs));\n"
    vs_new = "\t\tvs = _vs;\n\t\tvk_vs_name = _n;\n\t\tCHK_DX(HW.pDevice->SetVertexShader(vs));\n"
    if "\t\tvk_vs_name = _n;" not in rt:
        if vs_marker not in rt:
            raise RuntimeError("backend shader identity: set_VS marker not found")
        rt = rt.replace(vs_marker, vs_new, 1)

    indexed_handle_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV, startV, countV, startI, PC)"
    indexed_full_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, baseV, startV, countV, startI, PC)"
    indexed_legacy_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV, startV, countV, startI, PC)"
    if indexed_full_call not in rt:
        if indexed_handle_call in rt:
            rt = rt.replace(indexed_handle_call, indexed_full_call, 1)
        elif indexed_legacy_call in rt:
            rt = rt.replace(indexed_legacy_call, indexed_full_call, 1)
        else:
            raise RuntimeError("backend shader identity: indexed dispatch call marker not found")

    draw_handle_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV, PC)"
    draw_full_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, startV, PC)"
    draw_legacy_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV, PC)"
    if draw_full_call not in rt:
        if draw_handle_call in rt:
            rt = rt.replace(draw_handle_call, draw_full_call, 1)
        elif draw_legacy_call in rt:
            rt = rt.replace(draw_legacy_call, draw_full_call, 1)
        else:
            raise RuntimeError("backend shader identity: draw dispatch call marker not found")
    backend_runtime.write_text(rt, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    handle_export_indexed = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)'''
    full_export_indexed = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 base_vertex, u32 start_vertex,\n    u32 vertex_count, u32 start_index, u32 primitive_count)'''
    if "IDirect3DPixelShader9* pixel_shader,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name" not in vk:
        if handle_export_indexed not in vk:
            raise RuntimeError("backend shader identity: indexed export signature marker not found")
        vk = vk.replace(handle_export_indexed, full_export_indexed, 1)

    handle_export_draw = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    u32 start_vertex, u32 primitive_count)'''
    full_export_draw = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex, u32 primitive_count)'''
    if "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex" not in vk:
        if handle_export_draw not in vk:
            raise RuntimeError("backend shader identity: draw export signature marker not found")
        vk = vk.replace(handle_export_draw, full_export_draw, 1)

    indexed_guard = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_stride || !vertex_count || !primitive_count)'''
    indexed_guard_new = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name ||\n        !vertex_stride || !vertex_count || !primitive_count)'''
    if "!vertex_shader_name || !pixel_shader_name" not in vk:
        if indexed_guard not in vk:
            raise RuntimeError("backend shader identity: indexed guard marker not found")
        vk = vk.replace(indexed_guard, indexed_guard_new, 1)

    draw_guard = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_stride || !primitive_count)'''
    draw_guard_new = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer ||\n        !vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name ||\n        !vertex_stride || !primitive_count)'''
    draw_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(')
    if draw_start < 0:
        raise RuntimeError("backend shader identity: plain draw export missing")
    draw_slice = vk[draw_start:]
    if "!vertex_shader_name || !pixel_shader_name" not in draw_slice:
        if draw_guard not in draw_slice:
            raise RuntimeError("backend shader identity: draw guard marker not found")
        absolute_guard = draw_start + draw_slice.find(draw_guard)
        vk = vk[:absolute_guard] + draw_guard_new + vk[absolute_guard + len(draw_guard):]

    vk_source.write_text(vk, encoding="utf-8")

    required = {
        backend_h: (
            "LPCSTR vk_ps_name;", "LPCSTR vk_vs_name;",
            "IDirect3DVertexShader9* vertex_shader", "IDirect3DPixelShader9* pixel_shader",
            "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name",
        ),
        backend_runtime: (
            "vk_ps_name = _n;", "vk_vs_name = _n;",
            "ib, vs, ps, vk_vs_name, vk_ps_name",
            "vb_stride, vs, ps, vk_vs_name, vk_ps_name, startV",
        ),
        backend_source: ("vk_ps_name = NULL;", "vk_vs_name = NULL;"),
        vk_source: (
            "IDirect3DVertexShader9* vertex_shader", "IDirect3DPixelShader9* pixel_shader",
            "LPCSTR vertex_shader_name", "LPCSTR pixel_shader_name",
            "!vertex_shader_name || !pixel_shader_name",
        ),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"backend shader identity validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-shader-identity] VS/PS handles + release-safe names carried from RCache into renderer callback ABI")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry SHOC shader handles and stable names through the production Vulkan backend dispatch ABI.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
