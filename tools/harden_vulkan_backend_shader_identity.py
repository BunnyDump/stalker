from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    backend_h = root / "xr_3da" / "R_Backend.h"
    backend_runtime = root / "xr_3da" / "R_Backend_Runtime.h"
    vk_source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (backend_h, backend_runtime, vk_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = backend_h.read_text(encoding="utf-8")

    # Keep stable shader identities in release builds as well. The legacy debug-only
    # ps_name/vs_name fields are intentionally left alone; these names are renderer ABI state.
    state_marker = "\tIDirect3DVertexShader9* vs;\n"
    state_block = state_marker + "\tLPCSTR vk_ps_name;\n\tLPCSTR vk_vs_name;\n"
    if "LPCSTR vk_ps_name;" not in h:
        if state_marker not in h:
            raise RuntimeError("backend shader identity: shader-state marker not found")
        h = h.replace(state_marker, state_block, 1)

    old_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    IDirect3DIndexBuffer9* index_buffer, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count);'''
    new_indexed = '''typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DIndexBuffer9* index_buffer,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count);'''
    if "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DIndexBuffer9* index_buffer" not in h:
        if old_indexed not in h:
            raise RuntimeError("backend shader identity: indexed callback contract marker not found")
        h = h.replace(old_indexed, new_indexed, 1)

    old_draw = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    u32 start_vertex, u32 primitive_count);'''
    new_draw = '''typedef BOOL(__cdecl* xr_vk_backend_draw_fn)(D3DPRIMITIVETYPE primitive,\n    IDirect3DVertexDeclaration9* declaration, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex, u32 primitive_count);'''
    if "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex" not in h:
        if old_draw not in h:
            raise RuntimeError("backend shader identity: draw callback contract marker not found")
        h = h.replace(old_draw, new_draw, 1)
    backend_h.write_text(h, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")

    invalidate_marker = "\tps = NULL;\n\tvs = NULL;\n\tctable = NULL;\n"
    invalidate_new = "\tps = NULL;\n\tvs = NULL;\n\tvk_ps_name = NULL;\n\tvk_vs_name = NULL;\n\tctable = NULL;\n"
    if "\tvk_ps_name = NULL;" not in rt:
        if invalidate_marker not in rt:
            raise RuntimeError("backend shader identity: Invalidate shader marker not found")
        rt = rt.replace(invalidate_marker, invalidate_new, 1)

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

    indexed_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV, startV, countV, startI, PC)"
    indexed_call_new = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, vk_vs_name, vk_ps_name, ib, baseV, startV, countV, startI, PC)"
    if indexed_call_new not in rt:
        if indexed_call not in rt:
            raise RuntimeError("backend shader identity: indexed dispatch call marker not found")
        rt = rt.replace(indexed_call, indexed_call_new, 1)

    draw_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV, PC)"
    draw_call_new = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vk_vs_name, vk_ps_name, startV, PC)"
    if draw_call_new not in rt:
        if draw_call not in rt:
            raise RuntimeError("backend shader identity: draw dispatch call marker not found")
        rt = rt.replace(draw_call, draw_call_new, 1)
    backend_runtime.write_text(rt, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    old_export_indexed = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, IDirect3DIndexBuffer9* index_buffer,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)'''
    new_export_indexed = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    IDirect3DIndexBuffer9* index_buffer, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n    u32 start_index, u32 primitive_count)'''
    if "IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name," not in vk:
        if old_export_indexed not in vk:
            raise RuntimeError("backend shader identity: indexed export signature marker not found")
        vk = vk.replace(old_export_indexed, new_export_indexed, 1)

    old_export_draw = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, u32 start_vertex, u32 primitive_count)'''
    new_export_draw = '''    D3DPRIMITIVETYPE primitive, IDirect3DVertexDeclaration9* declaration,\n    IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    u32 start_vertex, u32 primitive_count)'''
    if "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    u32 start_vertex" not in vk:
        if old_export_draw not in vk:
            raise RuntimeError("backend shader identity: draw export signature marker not found")
        vk = vk.replace(old_export_draw, new_export_draw, 1)

    indexed_guard = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_stride || !vertex_count || !primitive_count)'''
    indexed_guard_new = '''    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !index_buffer ||\n        !vertex_stride || !vertex_count || !primitive_count || !vertex_shader_name || !pixel_shader_name)'''
    if "!vertex_shader_name || !pixel_shader_name" not in vk:
        if indexed_guard not in vk:
            raise RuntimeError("backend shader identity: indexed guard marker not found")
        vk = vk.replace(indexed_guard, indexed_guard_new, 1)

    draw_guard = "    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !vertex_stride || !primitive_count)\n"
    draw_guard_new = "    if (!xr_vk_bootstrap_runtime_ready() || !declaration || !vertex_buffer || !vertex_stride || !primitive_count ||\n        !vertex_shader_name || !pixel_shader_name)\n"
    if draw_guard_new not in vk:
        if draw_guard not in vk:
            raise RuntimeError("backend shader identity: draw guard marker not found")
        vk = vk.replace(draw_guard, draw_guard_new, 1)

    vk_source.write_text(vk, encoding="utf-8")

    required = {
        backend_h: (
            "LPCSTR vk_ps_name;", "LPCSTR vk_vs_name;",
            "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DIndexBuffer9* index_buffer",
            "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex",
        ),
        backend_runtime: (
            "vk_ps_name = _n;", "vk_vs_name = _n;",
            "vb_stride, vk_vs_name, vk_ps_name, ib",
            "vb_stride, vk_vs_name, vk_ps_name, startV",
        ),
        vk_source: (
            "LPCSTR vertex_shader_name", "LPCSTR pixel_shader_name",
            "!vertex_shader_name || !pixel_shader_name",
        ),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"backend shader identity validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-shader-identity] release-safe VS/PS names carried from RCache into renderer callback ABI")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry native SHOC shader identity through the production Vulkan backend dispatch ABI.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
