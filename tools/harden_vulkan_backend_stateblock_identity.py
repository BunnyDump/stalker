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
    old_indexed = "IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    u32 base_vertex"
    new_indexed = "IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n    IDirect3DStateBlock9* state_block, u32 base_vertex"
    indexed_callback_start = h.find("typedef BOOL(__cdecl* xr_vk_backend_draw_indexed_fn)")
    indexed_callback_end = h.find(");", indexed_callback_start)
    if indexed_callback_start < 0 or indexed_callback_end < 0:
        raise RuntimeError("backend state identity: indexed callback missing")
    indexed_callback = h[indexed_callback_start:indexed_callback_end]
    if "IDirect3DStateBlock9* state_block" not in indexed_callback:
        if old_indexed not in h:
            raise RuntimeError("backend state identity: indexed callback marker not found")
        h = h.replace(old_indexed, new_indexed, 1)

    old_plain = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex, u32 primitive_count);"
    new_plain = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 start_vertex, u32 primitive_count);"
    if "LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block" not in h:
        if old_plain not in h:
            raise RuntimeError("backend state identity: plain callback marker not found")
        h = h.replace(old_plain, new_plain, 1)
    backend_h.write_text(h, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")
    old_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, baseV, startV, countV, startI, PC)"
    new_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, state, baseV, startV, countV, startI, PC)"
    indexed_dispatch_start = rt.find("g_xr_vk_backend_draw_indexed(")
    indexed_dispatch_end = rt.find(")", indexed_dispatch_start)
    indexed_dispatch = rt[indexed_dispatch_start:indexed_dispatch_end]
    if indexed_dispatch_start < 0 or "vk_ps_name, state," not in indexed_dispatch:
        if old_call not in rt:
            raise RuntimeError("backend state identity: indexed dispatch marker not found")
        rt = rt.replace(old_call, new_call, 1)

    old_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, startV, PC)"
    new_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, state, startV, PC)"
    plain_dispatch_start = rt.find("g_xr_vk_backend_draw(")
    plain_dispatch_end = rt.find(")", plain_dispatch_start)
    plain_dispatch = rt[plain_dispatch_start:plain_dispatch_end]
    if plain_dispatch_start < 0 or "vk_ps_name, state," not in plain_dispatch:
        if old_call not in rt:
            raise RuntimeError("backend state identity: plain dispatch marker not found")
        rt = rt.replace(old_call, new_call, 1)
    backend_runtime.write_text(rt, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    old_indexed = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 base_vertex, u32 start_vertex,\n    u32 vertex_count"
    new_indexed = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 base_vertex, u32 start_vertex, u32 vertex_count"
    if "LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block" not in vk[vk.find("xrRender_vk_backend_draw_indexed"):]:
        if old_indexed not in vk:
            raise RuntimeError("backend state identity: indexed export marker not found")
        vk = vk.replace(old_indexed, new_indexed, 1)

    draw_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(')
    if draw_start < 0:
        raise RuntimeError("backend state identity: plain export missing")
    plain = vk[draw_start:]
    old_plain = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, u32 start_vertex, u32 primitive_count)"
    new_plain = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 start_vertex, u32 primitive_count)"
    if "IDirect3DStateBlock9* state_block" not in plain:
        if old_plain not in plain:
            raise RuntimeError("backend state identity: plain export marker not found")
        plain = plain.replace(old_plain, new_plain, 1)
        vk = vk[:draw_start] + plain

    # Reject a Vulkan path without the exact D3D state object that produced this draw.
    indexed_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    draw_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    indexed = vk[indexed_start:draw_start]
    if "!state_block" not in indexed:
        marker = "!vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name ||"
        if marker not in indexed:
            raise RuntimeError("backend state identity: indexed guard marker not found")
        indexed = indexed.replace(marker, marker + " !state_block ||", 1)
        vk = vk[:indexed_start] + indexed + vk[draw_start:]

    draw_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = vk[draw_start:]
    if "!state_block" not in plain:
        marker = "!vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name ||"
        if marker not in plain:
            raise RuntimeError("backend state identity: plain guard marker not found")
        plain = plain.replace(marker, marker + " !state_block ||", 1)
        vk = vk[:draw_start] + plain

    # Extend the pipeline key. The state block is an identity discriminator only for now;
    # its render-state payload is translated in the next bridge stage before live draw enablement.
    struct_marker = "        u64 vertex_declaration_identity;\n        u32 vertex_stride;"
    struct_new = "        u64 vertex_declaration_identity;\n        u64 state_block_identity;\n        u32 vertex_stride;"
    if "u64 state_block_identity;" not in vk:
        if struct_marker not in vk:
            raise RuntimeError("backend state identity: pipeline key struct marker not found")
        vk = vk.replace(struct_marker, struct_new, 1)

    eq_marker = "            a.vertex_declaration_identity == b.vertex_declaration_identity &&\n            a.vertex_stride"
    eq_new = "            a.vertex_declaration_identity == b.vertex_declaration_identity &&\n            a.state_block_identity == b.state_block_identity &&\n            a.vertex_stride"
    if "a.state_block_identity == b.state_block_identity" not in vk:
        if eq_marker not in vk:
            raise RuntimeError("backend state identity: key equality marker not found")
        vk = vk.replace(eq_marker, eq_new, 1)

    sig_marker = "IDirect3DVertexDeclaration9* declaration, u32 vertex_stride, D3DPRIMITIVETYPE primitive,\n        xr_vk_backend_pipeline_key& key"
    sig_new = "IDirect3DVertexDeclaration9* declaration, u32 vertex_stride, D3DPRIMITIVETYPE primitive,\n        IDirect3DStateBlock9* state_block, xr_vk_backend_pipeline_key& key"
    if "D3DPRIMITIVETYPE primitive,\n        IDirect3DStateBlock9* state_block" not in vk:
        if sig_marker not in vk:
            raise RuntimeError("backend state identity: key builder signature marker not found")
        vk = vk.replace(sig_marker, sig_new, 1)

    guard_marker = "if (!vertex_shader_identity || !pixel_shader_identity || !declaration || !vertex_stride)"
    guard_new = "if (!vertex_shader_identity || !pixel_shader_identity || !declaration || !vertex_stride || !state_block)"
    key_builder_start = vk.find("bool xr_vk_make_backend_pipeline_key(")
    key_builder_end = vk.find("VkPrimitiveTopology topology", key_builder_start)
    key_builder_guard = vk[key_builder_start:key_builder_end]
    if key_builder_start < 0 or "!state_block" not in key_builder_guard:
        if guard_marker not in vk:
            raise RuntimeError("backend state identity: key builder guard marker not found")
        vk = vk.replace(guard_marker, guard_new, 1)

    assign_marker = "        key.vertex_declaration_identity = declaration_identity;\n        key.vertex_stride = vertex_stride;"
    assign_new = "        key.vertex_declaration_identity = declaration_identity;\n        key.state_block_identity = static_cast<u64>(reinterpret_cast<size_t>(state_block));\n        key.vertex_stride = vertex_stride;"
    if "key.state_block_identity = static_cast<u64>(reinterpret_cast<size_t>(state_block));" not in vk:
        if assign_marker not in vk:
            raise RuntimeError("backend state identity: key assignment marker not found")
        vk = vk.replace(assign_marker, assign_new, 1)

    # Both export calls use the same key-builder text.
    call_old = "declaration, vertex_stride, primitive, pipeline_key, vertex_layout)"
    call_new = "declaration, vertex_stride, primitive, state_block, pipeline_key, vertex_layout)"
    state_aware_call = "declaration, vertex_stride, primitive, state_block,"
    if vk.count(state_aware_call) < 2:
        count = vk.count(call_old)
        if count != 2:
            raise RuntimeError(f"backend state identity: expected 2 key-builder calls, found {count}")
        vk = vk.replace(call_old, call_new)

    vk_source.write_text(vk, encoding="utf-8")

    final_h = backend_h.read_text(encoding="utf-8")
    final_rt = backend_runtime.read_text(encoding="utf-8")
    final_vk = vk_source.read_text(encoding="utf-8")
    for token in (
        "IDirect3DStateBlock9* state_block",
        "u64 state_block_identity;",
        "a.state_block_identity == b.state_block_identity",
        "reinterpret_cast<size_t>(state_block)",
        "primitive, state_block,",
    ):
        if token not in final_vk and token != "IDirect3DStateBlock9* state_block":
            raise RuntimeError(f"backend state identity validation failed: missing {token}")
    if "IDirect3DStateBlock9* state_block" not in final_h:
        raise RuntimeError("backend state identity validation failed: callback contract not state-aware")
    final_indexed_dispatch_start = final_rt.find("g_xr_vk_backend_draw_indexed(")
    final_indexed_dispatch_end = final_rt.find(")", final_indexed_dispatch_start)
    final_plain_dispatch_start = final_rt.find("g_xr_vk_backend_draw(")
    final_plain_dispatch_end = final_rt.find(")", final_plain_dispatch_start)
    final_indexed_dispatch = final_rt[final_indexed_dispatch_start:final_indexed_dispatch_end]
    final_plain_dispatch = final_rt[final_plain_dispatch_start:final_plain_dispatch_end]
    if "vk_ps_name, state," not in final_indexed_dispatch or "vk_ps_name, state," not in final_plain_dispatch:
        raise RuntimeError("backend state identity validation failed: RCache does not forward active state block")

    print("[vulkan-backend-state] D3D9 state-block identity carried through ABI and isolated in backend pipeline key")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prevent Vulkan pipeline aliasing across distinct SHOC D3D9 state blocks.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
