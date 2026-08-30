from __future__ import annotations

import argparse
from pathlib import Path

COMPARE_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral compare vocabulary. Transitional D3D9 conversion stays
// in one helper while Vulkan maps the same logical state to VkCompareOp.
enum XrCompareOp
{
    XR_COMPARE_LESS_EQUAL
};

static inline D3DCMPFUNC xr_compare_legacy(XrCompareOp op)
{
    switch (op)
    {
    case XR_COMPARE_LESS_EQUAL: return D3DCMP_LESSEQUAL;
    default: NODEFAULT; return D3DCMP_ALWAYS;
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
            raise RuntimeError("renderer-neutral topology block missing")
        end = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        end = text.find("\n", end) + 1
        text = text[:end] + COMPARE_BLOCK + text[end:]

    old = "RCache.set_Stencil(TRUE, D3DCMP_LESSEQUAL,"
    new = "RCache.set_Stencil(TRUE, xr_compare_legacy(XR_COMPARE_LESS_EQUAL),"
    count = text.count(old)
    if count:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    for token in ("enum XrCompareOp", "XR_COMPARE_LESS_EQUAL", "xr_compare_legacy"):
        if token not in final:
            raise RuntimeError(f"render-target compare validation missing {token}")
    if "RCache.set_Stencil(TRUE, D3DCMP_LESSEQUAL," in final:
        raise RuntimeError("direct D3DCMP_LESSEQUAL remains in stencil call")
    print(f"[vulkan-rendertarget-compare] centralized {count} stencil compare uses")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target compare state behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
