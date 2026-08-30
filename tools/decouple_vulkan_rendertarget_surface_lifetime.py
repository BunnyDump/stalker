from __future__ import annotations

import argparse
import re
from pathlib import Path

ADAPTER_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Legacy render-surface lifetime adapter. Render-target policy requests a
// logical shadow depth surface; COM creation/release stays at the DX9 edge.
static HRESULT xr_rt_legacy_create_shadow_depth_surface(u32 size, IDirect3DSurface9*& surface)
{
    return HW.pDevice->CreateDepthStencilSurface(size, size,
        xr_rt_legacy_format(XR_RT_FORMAT_D24),
        xr_rt_legacy_sample_mode(XR_RT_SAMPLE_SINGLE), 0, TRUE, &surface, NULL);
}

static void xr_rt_legacy_release_surface(IDirect3DSurface9*& surface)
{
    _RELEASE(surface);
}
//////////////////////////////////////////////////////////////////////////
'''

CREATE_PATTERN = re.compile(
    r"R_CHK\(HW\.pDevice->CreateDepthStencilSurface\(\s*size\s*,\s*size\s*,\s*"
    r"xr_rt_legacy_format\(XR_RT_FORMAT_D24\)\s*,\s*"
    r"xr_rt_legacy_sample_mode\(XR_RT_SAMPLE_SINGLE\)\s*,\s*0\s*,\s*TRUE\s*,\s*"
    r"&rt_smap_ZB\s*,\s*NULL\s*\)\);",
    re.S,
)


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")

    if "xr_rt_legacy_create_shadow_depth_surface" not in text:
        marker = "\nCRenderTarget::CRenderTarget()\n"
        if marker not in text:
            raise RuntimeError("render-target constructor marker not found")
        text = text.replace(marker, "\n" + ADAPTER_BLOCK + marker, 1)

    text, create_count = CREATE_PATTERN.subn(
        "R_CHK(xr_rt_legacy_create_shadow_depth_surface(size, rt_smap_ZB));", text, count=1
    )
    if create_count == 0 and "xr_rt_legacy_create_shadow_depth_surface(size, rt_smap_ZB)" not in text:
        raise RuntimeError("shadow depth surface creation marker not found")

    old_release = "\t_RELEASE(rt_smap_ZB);"
    new_release = "\txr_rt_legacy_release_surface(rt_smap_ZB);"
    if old_release in text:
        text = text.replace(old_release, new_release, 1)
    elif new_release not in text:
        raise RuntimeError("shadow depth surface release marker not found")

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in (
        "xr_rt_legacy_create_shadow_depth_surface",
        "xr_rt_legacy_release_surface",
        "R_CHK(xr_rt_legacy_create_shadow_depth_surface(size, rt_smap_ZB));",
        "xr_rt_legacy_release_surface(rt_smap_ZB);",
    ):
        if token not in final:
            raise RuntimeError(f"render-target surface lifetime validation missing {token}")

    ctor = final[final.find("CRenderTarget::CRenderTarget()") : final.find("CRenderTarget::~CRenderTarget()")]
    dtor = final[final.find("CRenderTarget::~CRenderTarget()") :]
    if "CreateDepthStencilSurface" in ctor:
        raise RuntimeError("direct depth surface creation remains in render-target constructor policy")
    if "_RELEASE(rt_smap_ZB)" in dtor:
        raise RuntimeError("direct shadow depth surface release remains in render-target destructor policy")
    print("[vulkan-rendertarget-surface-lifetime] shadow depth surface create/release isolated behind backend adapter")


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolate render-target shadow depth surface lifetime behind backend adapter.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
