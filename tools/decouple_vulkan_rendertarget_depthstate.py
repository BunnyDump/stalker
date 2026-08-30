from __future__ import annotations

import argparse
from pathlib import Path

STATE_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral depth/stencil state vocabulary. Transitional D3D9
// conversion remains localized while Vulkan maps the same logical state.
enum XrCompareOp
{
    XR_COMPARE_LESS_EQUAL
};

enum XrSampleMode
{
    XR_SAMPLE_NONE
};

static inline D3DCMPFUNC xr_compare_legacy(XrCompareOp op)
{
    switch (op)
    {
    case XR_COMPARE_LESS_EQUAL: return D3DCMP_LESSEQUAL;
    default: NODEFAULT; return D3DCMP_LESSEQUAL;
    }
}

static inline D3DMULTISAMPLE_TYPE xr_sample_legacy(XrSampleMode mode)
{
    switch (mode)
    {
    case XR_SAMPLE_NONE: return D3DMULTISAMPLE_NONE;
    default: NODEFAULT; return D3DMULTISAMPLE_NONE;
    }
}
//////////////////////////////////////////////////////////////////////////
'''


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8", errors="strict")
    if "enum XrCompareOp" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral primitive topology vocabulary."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral topology block missing before state decoupling")
        end = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        end = text.find("\n", end) + 1
        text = text[:end] + STATE_BLOCK + text[end:]

    replacements = (
        ("RCache.set_Stencil(TRUE, D3DCMP_LESSEQUAL,", "RCache.set_Stencil(TRUE, xr_compare_legacy(XR_COMPARE_LESS_EQUAL),"),
        ("D3DMULTISAMPLE_NONE, 0, TRUE, &rt_smap_ZB", "xr_sample_legacy(XR_SAMPLE_NONE), 0, TRUE, &rt_smap_ZB"),
    )
    applied = 0
    for old, new in replacements:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            applied += count

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrCompareOp", "enum XrSampleMode", "xr_compare_legacy", "xr_sample_legacy"):
        if token not in final:
            raise RuntimeError(f"render-target state validation missing {token}")
    if "RCache.set_Stencil(TRUE, D3DCMP_LESSEQUAL," in final:
        raise RuntimeError("direct D3DCMP_LESSEQUAL remains in stencil call")
    if "D3DMULTISAMPLE_NONE, 0, TRUE, &rt_smap_ZB" in final:
        raise RuntimeError("direct D3DMULTISAMPLE_NONE remains in shadow depth creation")
    if applied < 2:
        raise RuntimeError(f"expected both render-target state substitutions, got {applied}")
    print(f"[vulkan-rendertarget-depthstate] centralized {applied} depth/stencil state uses")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target depth/stencil state behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
