from __future__ import annotations

import argparse
from pathlib import Path

FORMAT_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral render-target format vocabulary. Transitional D3D9
// conversion remains centralized so Vulkan can map the same logical formats.
enum XrRtFormat
{
    XR_RT_FORMAT_RGBA16F,
    XR_RT_FORMAT_BGRA8,
    XR_RT_FORMAT_R5G6B5,
    XR_RT_FORMAT_R32F,
    XR_RT_FORMAT_D24,
    XR_RT_FORMAT_A8L8
};

static inline D3DFORMAT xr_rt_legacy_format(XrRtFormat format)
{
    switch (format)
    {
    case XR_RT_FORMAT_RGBA16F: return D3DFMT_A16B16G16R16F;
    case XR_RT_FORMAT_BGRA8: return D3DFMT_A8R8G8B8;
    case XR_RT_FORMAT_R5G6B5: return D3DFMT_R5G6B5;
    case XR_RT_FORMAT_R32F: return D3DFMT_R32F;
    case XR_RT_FORMAT_D24: return D3DFMT_D24X8;
    case XR_RT_FORMAT_A8L8: return D3DFMT_A8L8;
    default: NODEFAULT; return D3DFMT_UNKNOWN;
    }
}
//////////////////////////////////////////////////////////////////////////
'''

REPLACEMENTS = (
    ("D3DFMT_A16B16G16R16F", "xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F)"),
    ("D3DFMT_A8R8G8B8", "xr_rt_legacy_format(XR_RT_FORMAT_BGRA8)"),
    ("D3DFMT_R5G6B5", "xr_rt_legacy_format(XR_RT_FORMAT_R5G6B5)"),
    ("D3DFMT_R32F", "xr_rt_legacy_format(XR_RT_FORMAT_R32F)"),
    ("D3DFMT_D24X8", "xr_rt_legacy_format(XR_RT_FORMAT_D24)"),
    ("D3DFMT_A8L8", "xr_rt_legacy_format(XR_RT_FORMAT_A8L8)"),
)


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")
    if "enum XrRtFormat" not in text:
        marker = '#include "blender_luminance.h"\n'
        if marker not in text:
            raise RuntimeError("render-target format insertion marker not found")
        text = text.replace(marker, marker + FORMAT_BLOCK, 1)
    split = text.find("//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral render-target format vocabulary")
    body_start = text.find("//////////////////////////////////////////////////////////////////////////", split + 10)
    prefix, body = text[:body_start+78], text[body_start+78:]
    applied = 0
    for old, new in REPLACEMENTS:
        count = body.count(old)
        if count:
            body = body.replace(old, new)
            applied += count
    text = prefix + body
    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrRtFormat", "XR_RT_FORMAT_RGBA16F", "xr_rt_legacy_format"):
        if token not in final:
            raise RuntimeError(f"render-target format validation missing {token}")
    if applied < 12:
        raise RuntimeError(f"expected at least 12 render-target format substitutions, got {applied}")
    print(f"[vulkan-rendertarget-formats] centralized {applied} format uses")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
