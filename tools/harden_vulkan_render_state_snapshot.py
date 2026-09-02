from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    header = root / "xr_3da" / "tss_def.h"
    source = root / "xr_3da" / "tss_def.cpp"
    if not header.is_file() or not source.is_file():
        raise FileNotFoundError("Vulkan render-state snapshot requires materialized tss_def sources")

    h = header.read_text(encoding="utf-8")
    marker = "#pragma once\n\n"
    block = r'''#pragma once

// Immutable subset of the canonical D3D9 render-state code needed to build a Vulkan graphics pipeline.
// valid_mask is deliberately explicit: missing legacy state must fail closed instead of inheriting guessed defaults.
enum xr_vk_render_state_valid_bits
{
    XR_VK_RS_ZENABLE = 1u << 0,
    XR_VK_RS_ZWRITEENABLE = 1u << 1,
    XR_VK_RS_ZFUNC = 1u << 2,
    XR_VK_RS_ALPHABLENDENABLE = 1u << 3,
    XR_VK_RS_SRCBLEND = 1u << 4,
    XR_VK_RS_DESTBLEND = 1u << 5,
    XR_VK_RS_BLENDOP = 1u << 6,
    XR_VK_RS_COLORWRITEENABLE = 1u << 7
};

struct ENGINE_API xr_vk_render_state_snapshot
{
    u32 valid_mask;
    u32 z_enable;
    u32 z_write_enable;
    u32 z_func;
    u32 alpha_blend_enable;
    u32 src_blend;
    u32 dest_blend;
    u32 blend_op;
    u32 color_write_enable;
    u64 identity;
};

ENGINE_API BOOL xr_vk_query_render_state_snapshot(IDirect3DStateBlock9* state_block,
    xr_vk_render_state_snapshot& out_snapshot);

'''
    if "struct ENGINE_API xr_vk_render_state_snapshot" not in h:
        if marker not in h:
            raise RuntimeError("render-state snapshot: tss_def header marker missing")
        h = h.replace(marker, block, 1)
        header.write_text(h, encoding="utf-8")

    cpp = source.read_text(encoding="utf-8")
    impl_marker = '#include "tss_def.h"\n\n'
    impl = r'''#include "tss_def.h"

namespace
{
    struct xr_vk_state_snapshot_record
    {
        IDirect3DStateBlock9* state_block;
        xr_vk_render_state_snapshot snapshot;
    };

    xr_vector<xr_vk_state_snapshot_record> g_xr_vk_state_snapshots;

    void xr_vk_hash_u32(u64& hash, u32 value)
    {
        for (u32 i = 0; i < 4; ++i)
        {
            hash ^= static_cast<u64>(value & 0xffu);
            hash *= 1099511628211ull;
            value >>= 8;
        }
    }

    void xr_vk_register_render_state_snapshot(IDirect3DStateBlock9* state_block,
        const xr_vk_render_state_snapshot& snapshot)
    {
        if (!state_block)
            return;
        for (u32 i = 0; i < g_xr_vk_state_snapshots.size(); ++i)
        {
            if (g_xr_vk_state_snapshots[i].state_block != state_block)
                continue;
            g_xr_vk_state_snapshots[i].snapshot = snapshot;
            return;
        }
        xr_vk_state_snapshot_record record;
        record.state_block = state_block;
        record.snapshot = snapshot;
        g_xr_vk_state_snapshots.push_back(record);
    }
}

BOOL xr_vk_query_render_state_snapshot(IDirect3DStateBlock9* state_block,
    xr_vk_render_state_snapshot& out_snapshot)
{
    ZeroMemory(&out_snapshot, sizeof(out_snapshot));
    if (!state_block)
        return FALSE;
    // Prefer the newest registration so a recycled COM address can never resolve to stale metadata.
    for (u32 i = g_xr_vk_state_snapshots.size(); i > 0; --i)
    {
        if (g_xr_vk_state_snapshots[i - 1].state_block != state_block)
            continue;
        out_snapshot = g_xr_vk_state_snapshots[i - 1].snapshot;
        return TRUE;
    }
    return FALSE;
}

'''
    if "g_xr_vk_state_snapshots" not in cpp:
        if impl_marker not in cpp:
            raise RuntimeError("render-state snapshot: tss_def implementation marker missing")
        cpp = cpp.replace(impl_marker, impl, 1)

    end_marker = '''\tIDirect3DStateBlock9* SB = 0;
\tCHK_DX(HW.pDevice->EndStateBlock(&SB));
\treturn SB;
'''
    end_replacement = r'''	IDirect3DStateBlock9* SB = 0;
	CHK_DX(HW.pDevice->EndStateBlock(&SB));

    xr_vk_render_state_snapshot snapshot = {};
    u64 snapshot_hash = 1469598103934665603ull;
    for (u32 i = 0; i < States.size(); ++i)
    {
        const State& S = States[i];
        if (S.type != 0)
            continue;

        u32 bit = 0;
        u32* target = NULL;
        switch ((D3DRENDERSTATETYPE)S.v1)
        {
        case D3DRS_ZENABLE: bit = XR_VK_RS_ZENABLE; target = &snapshot.z_enable; break;
        case D3DRS_ZWRITEENABLE: bit = XR_VK_RS_ZWRITEENABLE; target = &snapshot.z_write_enable; break;
        case D3DRS_ZFUNC: bit = XR_VK_RS_ZFUNC; target = &snapshot.z_func; break;
        case D3DRS_ALPHABLENDENABLE: bit = XR_VK_RS_ALPHABLENDENABLE; target = &snapshot.alpha_blend_enable; break;
        case D3DRS_SRCBLEND: bit = XR_VK_RS_SRCBLEND; target = &snapshot.src_blend; break;
        case D3DRS_DESTBLEND: bit = XR_VK_RS_DESTBLEND; target = &snapshot.dest_blend; break;
        case D3DRS_BLENDOP: bit = XR_VK_RS_BLENDOP; target = &snapshot.blend_op; break;
        case D3DRS_COLORWRITEENABLE: bit = XR_VK_RS_COLORWRITEENABLE; target = &snapshot.color_write_enable; break;
        default: break;
        }
        if (!bit || !target)
            continue;
        snapshot.valid_mask |= bit;
        *target = S.v2;
        xr_vk_hash_u32(snapshot_hash, S.v1);
        xr_vk_hash_u32(snapshot_hash, S.v2);
    }
    snapshot.identity = snapshot_hash ? snapshot_hash : 1ull;
    xr_vk_register_render_state_snapshot(SB, snapshot);
	return SB;
'''
    if "xr_vk_register_render_state_snapshot(SB, snapshot);" not in cpp:
        if end_marker not in cpp:
            raise RuntimeError("render-state snapshot: state-block finalization marker missing")
        cpp = cpp.replace(end_marker, end_replacement, 1)

    source.write_text(cpp, encoding="utf-8")

    final_h = header.read_text(encoding="utf-8")
    final_cpp = source.read_text(encoding="utf-8")
    required_h = (
        "xr_vk_render_state_valid_bits", "xr_vk_render_state_snapshot",
        "XR_VK_RS_ZENABLE", "XR_VK_RS_ALPHABLENDENABLE", "XR_VK_RS_COLORWRITEENABLE",
        "xr_vk_query_render_state_snapshot",
    )
    required_cpp = (
        "g_xr_vk_state_snapshots", "xr_vk_register_render_state_snapshot",
        "D3DRS_ZENABLE", "D3DRS_ZWRITEENABLE", "D3DRS_ZFUNC",
        "D3DRS_ALPHABLENDENABLE", "D3DRS_SRCBLEND", "D3DRS_DESTBLEND", "D3DRS_BLENDOP",
        "D3DRS_COLORWRITEENABLE", "snapshot.identity", "xr_vk_register_render_state_snapshot(SB, snapshot);",
    )
    for token in required_h:
        if token not in final_h:
            raise RuntimeError(f"render-state snapshot header validation failed: missing {token}")
    for token in required_cpp:
        if token not in final_cpp:
            raise RuntimeError(f"render-state snapshot implementation validation failed: missing {token}")

    print("[vulkan-render-state-snapshot] canonical D3D9 depth/blend/color-write state snapshots registered per immutable state block")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture canonical SHOC D3D9 render states for later Vulkan pipeline translation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
