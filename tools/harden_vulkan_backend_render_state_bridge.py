from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    h_path = root / "xr_3da" / "R_Backend.h"
    rt_path = root / "xr_3da" / "R_Backend_Runtime.h"
    vk_path = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (h_path, rt_path, vk_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = h_path.read_text(encoding="utf-8")
    if '#include "tss_def.h"' not in h:
        marker = '#include "fvf.h"\n'
        if marker not in h:
            raise RuntimeError("backend render-state bridge: include marker missing")
        h = h.replace(marker, marker + '#include "tss_def.h"\n', 1)

    state_field = "\tIDirect3DStateBlock9* state;\n"
    state_fields = state_field + "\txr_vk_render_state_snapshot vk_render_state_snapshot;\n\tBOOL vk_render_state_snapshot_valid;\n"
    if "vk_render_state_snapshot_valid" not in h:
        if state_field not in h:
            raise RuntimeError("backend render-state bridge: backend state field missing")
        h = h.replace(state_field, state_fields, 1)

    # State-block hardening has already extended both callback contracts. Add the immutable snapshot beside it.
    indexed_old = "IDirect3DStateBlock9* state_block, u32 base_vertex"
    indexed_new = "IDirect3DStateBlock9* state_block, const xr_vk_render_state_snapshot* render_state, u32 base_vertex"
    if indexed_new not in h:
        if indexed_old not in h:
            raise RuntimeError("backend render-state bridge: indexed ABI marker missing")
        h = h.replace(indexed_old, indexed_new, 1)
    plain_old = "LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 start_vertex"
    plain_new = "LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    const xr_vk_render_state_snapshot* render_state, u32 start_vertex"
    if plain_new not in h:
        if plain_old not in h:
            raise RuntimeError("backend render-state bridge: plain ABI marker missing")
        h = h.replace(plain_old, plain_new, 1)
    h_path.write_text(h, encoding="utf-8")

    rt = rt_path.read_text(encoding="utf-8")
    set_state_old = '''\t\tstate = _state;\n\t\tstate->Apply();\n'''
    set_state_new = '''\t\tstate = _state;\n\t\tZeroMemory(&vk_render_state_snapshot, sizeof(vk_render_state_snapshot));\n\t\tvk_render_state_snapshot_valid = xr_vk_query_render_state_snapshot(state, vk_render_state_snapshot);\n\t\tstate->Apply();\n'''
    if "xr_vk_query_render_state_snapshot(state, vk_render_state_snapshot)" not in rt:
        if set_state_old not in rt:
            raise RuntimeError("backend render-state bridge: set_States marker missing")
        rt = rt.replace(set_state_old, set_state_new, 1)

    indexed_old = "vk_ps_name, state, baseV"
    indexed_new = "vk_ps_name, state, vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, baseV"
    if indexed_new not in rt:
        if indexed_old not in rt:
            raise RuntimeError("backend render-state bridge: indexed dispatch marker missing")
        rt = rt.replace(indexed_old, indexed_new, 1)
    plain_old = "vk_ps_name, state, startV"
    plain_new = "vk_ps_name, state, vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, startV"
    if plain_new not in rt:
        if plain_old not in rt:
            raise RuntimeError("backend render-state bridge: plain dispatch marker missing")
        rt = rt.replace(plain_old, plain_new, 1)
    rt_path.write_text(rt, encoding="utf-8")

    vk = vk_path.read_text(encoding="utf-8")
    indexed_old = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 base_vertex"
    indexed_new = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    const xr_vk_render_state_snapshot* render_state, u32 base_vertex"
    if indexed_new not in vk:
        if indexed_old not in vk:
            raise RuntimeError("backend render-state bridge: indexed export marker missing")
        vk = vk.replace(indexed_old, indexed_new, 1)

    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(')
    if plain_start < 0:
        raise RuntimeError("backend render-state bridge: plain export missing")
    plain = vk[plain_start:]
    plain_old = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    u32 start_vertex"
    plain_new = "LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n    const xr_vk_render_state_snapshot* render_state, u32 start_vertex"
    if plain_new not in plain:
        if plain_old not in plain:
            raise RuntimeError("backend render-state bridge: plain export marker missing")
        plain = plain.replace(plain_old, plain_new, 1)
        vk = vk[:plain_start] + plain

    # Both exports must reject draws whose canonical state snapshot is missing.
    indexed_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    indexed = vk[indexed_start:plain_start]
    if "!render_state" not in indexed:
        marker = "!vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name || !state_block ||"
        if marker not in indexed:
            raise RuntimeError("backend render-state bridge: indexed guard marker missing")
        indexed = indexed.replace(marker, marker + " !render_state ||", 1)
        vk = vk[:indexed_start] + indexed + vk[plain_start:]

    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = vk[plain_start:]
    if "!render_state" not in plain:
        marker = "!vertex_shader || !pixel_shader || !vertex_shader_name || !pixel_shader_name || !state_block ||"
        if marker not in plain:
            raise RuntimeError("backend render-state bridge: plain guard marker missing")
        plain = plain.replace(marker, marker + " !render_state ||", 1)
        vk = vk[:plain_start] + plain

    # Add canonical render-state identity to the pipeline key in addition to temporary COM identity isolation.
    key_marker = "        u64 state_block_identity;\n        u32 vertex_stride;"
    key_new = "        u64 state_block_identity;\n        u64 render_state_identity;\n        u32 vertex_stride;"
    if "u64 render_state_identity;" not in vk:
        if key_marker not in vk:
            raise RuntimeError("backend render-state bridge: pipeline key marker missing")
        vk = vk.replace(key_marker, key_new, 1)

    eq_marker = "            a.state_block_identity == b.state_block_identity &&\n            a.vertex_stride"
    eq_new = "            a.state_block_identity == b.state_block_identity &&\n            a.render_state_identity == b.render_state_identity &&\n            a.vertex_stride"
    if "a.render_state_identity == b.render_state_identity" not in vk:
        if eq_marker not in vk:
            raise RuntimeError("backend render-state bridge: pipeline equality marker missing")
        vk = vk.replace(eq_marker, eq_new, 1)

    sig_marker = "IDirect3DStateBlock9* state_block, xr_vk_backend_pipeline_key& key"
    sig_new = "IDirect3DStateBlock9* state_block, const xr_vk_render_state_snapshot* render_state,\n        xr_vk_backend_pipeline_key& key"
    if sig_new not in vk:
        if sig_marker not in vk:
            raise RuntimeError("backend render-state bridge: key builder signature marker missing")
        vk = vk.replace(sig_marker, sig_new, 1)

    guard_marker = "|| !state_block)"
    guard_new = "|| !state_block || !render_state || !render_state->identity)"
    if guard_new not in vk:
        if guard_marker not in vk:
            raise RuntimeError("backend render-state bridge: key builder guard marker missing")
        vk = vk.replace(guard_marker, guard_new, 1)

    assign_marker = "        key.state_block_identity = static_cast<u64>(reinterpret_cast<size_t>(state_block));\n        key.vertex_stride"
    assign_new = "        key.state_block_identity = static_cast<u64>(reinterpret_cast<size_t>(state_block));\n        key.render_state_identity = render_state->identity;\n        key.vertex_stride"
    if "key.render_state_identity = render_state->identity;" not in vk:
        if assign_marker not in vk:
            raise RuntimeError("backend render-state bridge: key assignment marker missing")
        vk = vk.replace(assign_marker, assign_new, 1)

    call_old = "primitive, state_block, pipeline_key, vertex_layout)"
    call_new = "primitive, state_block, render_state, pipeline_key, vertex_layout)"
    if call_new not in vk:
        count = vk.count(call_old)
        if count != 2:
            raise RuntimeError(f"backend render-state bridge: expected two key-builder calls, found {count}")
        vk = vk.replace(call_old, call_new)

    vk_path.write_text(vk, encoding="utf-8")

    final_h = h_path.read_text(encoding="utf-8")
    final_rt = rt_path.read_text(encoding="utf-8")
    final_vk = vk_path.read_text(encoding="utf-8")
    for token in (
        "vk_render_state_snapshot", "vk_render_state_snapshot_valid",
        "xr_vk_query_render_state_snapshot(state, vk_render_state_snapshot)",
        "const xr_vk_render_state_snapshot* render_state",
        "u64 render_state_identity;", "key.render_state_identity = render_state->identity;",
        "primitive, state_block, render_state, pipeline_key, vertex_layout",
    ):
        if token not in final_h and token not in final_rt and token not in final_vk:
            raise RuntimeError(f"backend render-state bridge validation failed: missing {token}")

    print("[vulkan-backend-render-state] canonical state snapshots carried through CBackend ABI and included in fail-closed pipeline identity")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry immutable SHOC render-state snapshots from CBackend into Vulkan pipeline lookup.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
