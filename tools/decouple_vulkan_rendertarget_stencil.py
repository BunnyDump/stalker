from __future__ import annotations

import argparse
from pathlib import Path

COMPARE_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral depth/stencil compare vocabulary. The DX9 fallback
// conversion is kept at one adapter boundary; Vulkan maps this to VkCompareOp.
enum XrCompareFunc
{
    XR_COMPARE_LESS_EQUAL
};

static inline D3DCMPFUNC xr_legacy_compare_func(XrCompareFunc func)
{
    switch (func)
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

    if "enum XrCompareFunc" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral vertex declaration for helper passes."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral declaration block missing before compare decoupling")
        close = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        close = text.find("\n", close) + 1
        text = text[:close] + COMPARE_BLOCK + text[close:]

    old = "RCache.set_Stencil(TRUE, D3DCMP_LESSEQUAL, dwLightMarkerID, 0xff, 0x00);"
    new = "RCache.set_Stencil(TRUE, xr_legacy_compare_func(XR_COMPARE_LESS_EQUAL), dwLightMarkerID, 0xff, 0x00);"
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("stencil compare marker not found")

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrCompareFunc", "XR_COMPARE_LESS_EQUAL", "xr_legacy_compare_func"):
        if token not in final:
            raise RuntimeError(f"render-target compare validation missing {token}")

    adapter_end = final.find("//////////////////////////////////////////////////////////////////////////", final.find("enum XrCompareFunc") + 1)
    body = final[adapter_end + len("//////////////////////////////////////////////////////////////////////////"):]
    if "D3DCMP_" in body:
        raise RuntimeError("direct D3DCMP token remains in render-target policy")
    print("[vulkan-rendertarget-stencil] stencil compare function centralized behind renderer-neutral vocabulary")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target stencil comparison behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
