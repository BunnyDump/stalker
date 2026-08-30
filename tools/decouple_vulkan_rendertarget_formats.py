from __future__ import annotations

import argparse
from pathlib import Path

FORMAT_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral render-target format vocabulary. The transitional
// D3D9 fallback conversion is intentionally centralized here; Vulkan code
// can map the same logical formats to VkFormat without leaking D3DFORMAT
// through the render-target construction policy.
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

EXACT_REPLACEMENTS = (
    ("rt_Position.create(r2_RT_P, w, h, D3DFMT_A16B16G16R16F);", "rt_Position.create(r2_RT_P, w, h, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_Normal.create(r2_RT_N, w, h, D3DFMT_A16B16G16R16F);", "rt_Normal.create(r2_RT_N, w, h, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_Color.create(r2_RT_albedo, w, h, D3DFMT_A8R8G8B8);", "rt_Color.create(r2_RT_albedo, w, h, xr_rt_legacy_format(XR_RT_FORMAT_BGRA8));"),
    ("rt_Accumulator.create(r2_RT_accum, w, h, D3DFMT_A16B16G16R16F);", "rt_Accumulator.create(r2_RT_accum, w, h, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_Color.create(r2_RT_albedo, w, h, D3DFMT_A16B16G16R16F);", "rt_Color.create(r2_RT_albedo, w, h, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_Accumulator_temp.create(r2_RT_accum_temp, w, h, D3DFMT_A16B16G16R16F);", "rt_Accumulator_temp.create(r2_RT_accum_temp, w, h, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_Generic_0.create(r2_RT_generic0, w, h, D3DFMT_A8R8G8B8);", "rt_Generic_0.create(r2_RT_generic0, w, h, xr_rt_legacy_format(XR_RT_FORMAT_BGRA8));"),
    ("rt_Generic_1.create(r2_RT_generic1, w, h, D3DFMT_A8R8G8B8);", "rt_Generic_1.create(r2_RT_generic1, w, h, xr_rt_legacy_format(XR_RT_FORMAT_BGRA8));"),
    ("D3DFORMAT nullrt = D3DFMT_R5G6B5;", "D3DFORMAT nullrt = xr_rt_legacy_format(XR_RT_FORMAT_R5G6B5);"),
    ("rt_smap_surf.create(r2_RT_smap_surf, size, size, D3DFMT_R32F);", "rt_smap_surf.create(r2_RT_smap_surf, size, size, xr_rt_legacy_format(XR_RT_FORMAT_R32F));"),
    ("D3DFORMAT fmt = D3DFMT_A8R8G8B8;", "D3DFORMAT fmt = xr_rt_legacy_format(XR_RT_FORMAT_BGRA8);"),
    ("rt_LUM_64.create(r2_RT_luminance_t64, 64, 64, D3DFMT_A16B16G16R16F);", "rt_LUM_64.create(r2_RT_luminance_t64, 64, 64, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_LUM_8.create(r2_RT_luminance_t8, 8, 8, D3DFMT_A16B16G16R16F);", "rt_LUM_8.create(r2_RT_luminance_t8, 8, 8, xr_rt_legacy_format(XR_RT_FORMAT_RGBA16F));"),
    ("rt_LUM_pool[it].create(name, 1, 1, D3DFMT_R32F);", "rt_LUM_pool[it].create(name, 1, 1, xr_rt_legacy_format(XR_RT_FORMAT_R32F));"),
    ("D3DFMT_D24X8, D3DMULTISAMPLE_NONE", "xr_rt_legacy_format(XR_RT_FORMAT_D24), D3DMULTISAMPLE_NONE"),
    ("D3DFMT_A8L8,", "xr_rt_legacy_format(XR_RT_FORMAT_A8L8),"),
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

    applied = 0
    for old, new in EXACT_REPLACEMENTS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            applied += count

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrRtFormat", "XR_RT_FORMAT_RGBA16F", "xr_rt_legacy_format"):
        if token not in final:
            raise RuntimeError(f"render-target format validation missing {token}")
    if applied < 12:
        raise RuntimeError(f"render-target format decoupling expected at least 12 substitutions, applied {applied}")
    print(f"[vulkan-rendertarget-formats] centralized {applied} legacy format uses behind renderer-neutral formats")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize legacy render-target formats behind renderer-neutral logical formats.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
