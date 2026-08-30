from __future__ import annotations

import argparse
import re
from pathlib import Path

HANDLE_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Transitional render-target resource handles. The class and its policy use
// renderer-local names; only this boundary exposes the legacy D3D9 pointer
// types. A later step can replace these aliases with Vulkan-backed handles.
typedef IDirect3DSurface9* XrRtSurfaceHandle;
typedef IDirect3DVolumeTexture9* XrRtVolumeTextureHandle;
typedef IDirect3DTexture9* XrRtTexture2DHandle;
typedef IDirect3DVertexBuffer9* XrRtVertexBufferHandle;
typedef IDirect3DIndexBuffer9* XrRtIndexBufferHandle;
//////////////////////////////////////////////////////////////////////////
'''

HEADER_REPLACEMENTS = (
    ("\tIDirect3DSurface9* rt_smap_ZB;", "\tXrRtSurfaceHandle rt_smap_ZB;"),
    ("\tIDirect3DVolumeTexture9* t_material_surf;", "\tXrRtVolumeTextureHandle t_material_surf;"),
    ("\tIDirect3DTexture9* t_noise_surf[TEX_jitter_count];", "\tXrRtTexture2DHandle t_noise_surf[TEX_jitter_count];"),
    ("\tIDirect3DVertexBuffer9* g_accum_point_vb;", "\tXrRtVertexBufferHandle g_accum_point_vb;"),
    ("\tIDirect3DIndexBuffer9* g_accum_point_ib;", "\tXrRtIndexBufferHandle g_accum_point_ib;"),
    ("\tIDirect3DVertexBuffer9* g_accum_omnip_vb;", "\tXrRtVertexBufferHandle g_accum_omnip_vb;"),
    ("\tIDirect3DIndexBuffer9* g_accum_omnip_ib;", "\tXrRtIndexBufferHandle g_accum_omnip_ib;"),
    ("\tIDirect3DVertexBuffer9* g_accum_spot_vb;", "\tXrRtVertexBufferHandle g_accum_spot_vb;"),
    ("\tIDirect3DIndexBuffer9* g_accum_spot_ib;", "\tXrRtIndexBufferHandle g_accum_spot_ib;"),
)


def decouple(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    header = renderer / "r2_rendertarget.h"
    source = renderer / "r2_rendertarget.cpp"
    for path in (header, source):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = header.read_text(encoding="utf-8", errors="strict")
    for old, new in HEADER_REPLACEMENTS:
        if old in h:
            h = h.replace(old, new, 1)
        elif new not in h:
            raise RuntimeError(f"render-target handle field marker not found: {old}")

    h = h.replace(
        "\tvoid u_setrt(const ref_rt& _1, const ref_rt& _2, const ref_rt& _3, IDirect3DSurface9* zb);",
        "\tvoid u_setrt(const ref_rt& _1, const ref_rt& _2, const ref_rt& _3, XrRtSurfaceHandle zb);",
        1,
    )
    h = h.replace(
        "\tvoid u_setrt(u32 W, u32 H, IDirect3DSurface9* _1, IDirect3DSurface9* _2, IDirect3DSurface9* _3,\n\t\t\t\t IDirect3DSurface9* zb);",
        "\tvoid u_setrt(u32 W, u32 H, XrRtSurfaceHandle _1, XrRtSurfaceHandle _2, XrRtSurfaceHandle _3,\n\t\t\t\t XrRtSurfaceHandle zb);",
        1,
    )

    if "typedef IDirect3DSurface9* XrRtSurfaceHandle;" not in h:
        marker = "class light;\n"
        if marker not in h:
            raise RuntimeError("render-target handle insertion marker not found")
        h = h.replace(marker, marker + "\n" + HANDLE_BLOCK, 1)
    header.write_text(h, encoding="utf-8")

    cpp = source.read_text(encoding="utf-8", errors="strict")
    cpp, count1 = re.subn(
        r"void CRenderTarget::u_setrt\(const ref_rt& _1, const ref_rt& _2, const ref_rt& _3, IDirect3DSurface9\* zb\)",
        "void CRenderTarget::u_setrt(const ref_rt& _1, const ref_rt& _2, const ref_rt& _3, XrRtSurfaceHandle zb)",
        cpp,
        count=1,
    )
    cpp, count2 = re.subn(
        r"void CRenderTarget::u_setrt\(u32 W, u32 H, IDirect3DSurface9\* _1, IDirect3DSurface9\* _2, IDirect3DSurface9\* _3,\s*IDirect3DSurface9\* zb\)",
        "void CRenderTarget::u_setrt(u32 W, u32 H, XrRtSurfaceHandle _1, XrRtSurfaceHandle _2, XrRtSurfaceHandle _3,\n\t\t\t\t\t\t\tXrRtSurfaceHandle zb)",
        cpp,
        count=1,
        flags=re.S,
    )
    if count1 == 0 and "XrRtSurfaceHandle zb)" not in cpp:
        raise RuntimeError("first u_setrt surface handle definition not converted")
    if count2 == 0 and "XrRtSurfaceHandle _1" not in cpp:
        raise RuntimeError("second u_setrt surface handle definition not converted")
    source.write_text(cpp, encoding="utf-8")

    final_h = header.read_text(encoding="utf-8")
    class_pos = final_h.find("class CRenderTarget")
    if class_pos < 0:
        raise RuntimeError("CRenderTarget class missing after handle conversion")
    class_text = final_h[class_pos:]
    if "IDirect3D" in class_text:
        raise RuntimeError("direct IDirect3D pointer type remains in CRenderTarget class policy")
    for token in (
        "XrRtSurfaceHandle rt_smap_ZB",
        "XrRtVolumeTextureHandle t_material_surf",
        "XrRtTexture2DHandle t_noise_surf",
        "XrRtVertexBufferHandle g_accum_point_vb",
        "XrRtIndexBufferHandle g_accum_point_ib",
    ):
        if token not in final_h:
            raise RuntimeError(f"render-target handle validation missing {token}")

    top = source.read_text(encoding="utf-8")
    policy_end = top.find("void CRenderTarget::u_stencil_optimize")
    if policy_end < 0:
        raise RuntimeError("u_stencil_optimize marker missing after handle conversion")
    if "IDirect3DSurface9" in top[:policy_end]:
        raise RuntimeError("direct surface type remains in u_setrt policy signatures")
    print("[vulkan-rendertarget-handles] centralized render-target COM pointer types behind transitional handles")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target D3D9 pointer types behind transitional resource handles.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
