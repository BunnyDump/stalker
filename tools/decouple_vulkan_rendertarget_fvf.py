from __future__ import annotations

import argparse
from pathlib import Path

FVF_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral vertex-layout vocabulary for render-target helper geometry.
// Only this transitional adapter knows the legacy D3D9 FVF encoding; Vulkan
// maps the same logical layouts to VkVertexInput* descriptions.
enum XrRtVertexLayout
{
    XR_RT_VERTEX_POSITION,
    XR_RT_VERTEX_BLOOM_BUILD,
    XR_RT_VERTEX_BLOOM_FILTER,
    XR_RT_VERTEX_AA_BLUR,
    XR_RT_VERTEX_AA,
    XR_RT_VERTEX_POSTPROCESS
};

static inline u32 xr_rt_legacy_fvf(XrRtVertexLayout layout)
{
    switch (layout)
    {
    case XR_RT_VERTEX_POSITION:
        return D3DFVF_XYZ;
    case XR_RT_VERTEX_BLOOM_BUILD:
    case XR_RT_VERTEX_AA_BLUR:
        return D3DFVF_XYZRHW | D3DFVF_TEX4 |
            D3DFVF_TEXCOORDSIZE2(0) | D3DFVF_TEXCOORDSIZE2(1) |
            D3DFVF_TEXCOORDSIZE2(2) | D3DFVF_TEXCOORDSIZE2(3);
    case XR_RT_VERTEX_BLOOM_FILTER:
        return D3DFVF_XYZRHW | D3DFVF_TEX8 |
            D3DFVF_TEXCOORDSIZE4(0) | D3DFVF_TEXCOORDSIZE4(1) |
            D3DFVF_TEXCOORDSIZE4(2) | D3DFVF_TEXCOORDSIZE4(3) |
            D3DFVF_TEXCOORDSIZE4(4) | D3DFVF_TEXCOORDSIZE4(5) |
            D3DFVF_TEXCOORDSIZE4(6) | D3DFVF_TEXCOORDSIZE4(7);
    case XR_RT_VERTEX_AA:
        return D3DFVF_XYZRHW | D3DFVF_TEX7 |
            D3DFVF_TEXCOORDSIZE2(0) | D3DFVF_TEXCOORDSIZE2(1) |
            D3DFVF_TEXCOORDSIZE2(2) | D3DFVF_TEXCOORDSIZE2(3) |
            D3DFVF_TEXCOORDSIZE2(4) | D3DFVF_TEXCOORDSIZE4(5) |
            D3DFVF_TEXCOORDSIZE4(6);
    case XR_RT_VERTEX_POSTPROCESS:
        return D3DFVF_XYZRHW | D3DFVF_DIFFUSE | D3DFVF_SPECULAR | D3DFVF_TEX3;
    default:
        NODEFAULT;
        return 0;
    }
}
//////////////////////////////////////////////////////////////////////////
'''

EXACT_REPLACEMENTS = (
    ("g_accum_point.create(D3DFVF_XYZ, g_accum_point_vb, g_accum_point_ib);",
     "g_accum_point.create(xr_rt_legacy_fvf(XR_RT_VERTEX_POSITION), g_accum_point_vb, g_accum_point_ib);"),
    ("g_accum_omnipart.create(D3DFVF_XYZ, g_accum_omnip_vb, g_accum_omnip_ib);",
     "g_accum_omnipart.create(xr_rt_legacy_fvf(XR_RT_VERTEX_POSITION), g_accum_omnip_vb, g_accum_omnip_ib);"),
    ("g_accum_spot.create(D3DFVF_XYZ, g_accum_spot_vb, g_accum_spot_ib);",
     "g_accum_spot.create(xr_rt_legacy_fvf(XR_RT_VERTEX_POSITION), g_accum_spot_vb, g_accum_spot_ib);"),
    ("g_postprocess.create(D3DFVF_XYZRHW | D3DFVF_DIFFUSE | D3DFVF_SPECULAR | D3DFVF_TEX3, RCache.Vertex.Buffer(),",
     "g_postprocess.create(xr_rt_legacy_fvf(XR_RT_VERTEX_POSTPROCESS), RCache.Vertex.Buffer(),"),
)


def _replace_decl(text: str, variable: str, layout: str, next_anchor: str) -> tuple[str, bool]:
    marker = f"u32 {variable} ="
    start = text.find(marker)
    if start < 0:
        return text, False
    end = text.find(next_anchor, start)
    if end < 0:
        raise RuntimeError(f"FVF declaration terminator not found for {variable}")
    semicolon = text.rfind(";", start, end)
    if semicolon < start:
        raise RuntimeError(f"FVF declaration semicolon not found for {variable}")
    replacement = f"u32 {variable} = xr_rt_legacy_fvf({layout});"
    return text[:start] + replacement + text[semicolon + 1:], True


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")

    if "enum XrRtVertexLayout" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral primitive topology vocabulary."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral topology block missing before FVF decoupling")
        close = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        close = text.find("\n", close) + 1
        text = text[:close] + FVF_BLOCK + text[close:]

    applied = 0
    for old, new in EXACT_REPLACEMENTS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            applied += count

    for variable, layout, anchor in (
        ("fvf_build", "XR_RT_VERTEX_BLOOM_BUILD", "u32 fvf_filter"),
        ("fvf_filter", "XR_RT_VERTEX_BLOOM_FILTER", "rt_Bloom_1.create"),
        ("fvf_aa_blur", "XR_RT_VERTEX_AA_BLUR", "g_aa_blur.create"),
        ("fvf_aa_AA", "XR_RT_VERTEX_AA", "g_aa_AA.create"),
    ):
        text, changed = _replace_decl(text, variable, layout, anchor)
        applied += int(changed)

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrRtVertexLayout", "xr_rt_legacy_fvf", "XR_RT_VERTEX_BLOOM_FILTER", "XR_RT_VERTEX_POSTPROCESS"):
        if token not in final:
            raise RuntimeError(f"render-target FVF validation missing {token}")
    if applied < 8:
        raise RuntimeError(f"expected at least 8 render-target FVF conversions, got {applied}")

    adapter_end = final.find("//////////////////////////////////////////////////////////////////////////", final.find("enum XrRtVertexLayout") + 1)
    body = final[adapter_end + len("//////////////////////////////////////////////////////////////////////////"):]
    if "D3DFVF_" in body:
        raise RuntimeError("direct D3DFVF tokens remain in render-target policy after FVF decoupling")
    print(f"[vulkan-rendertarget-fvf] centralized {applied} FVF/layout uses")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target FVF layouts behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
