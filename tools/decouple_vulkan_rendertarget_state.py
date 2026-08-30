from __future__ import annotations

import argparse
from pathlib import Path

STATE_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral clear/sample vocabulary used by render-target policy.
enum XrRtClearMask
{
    XR_RT_CLEAR_COLOR = 1u
};

enum XrRtSampleMode
{
    XR_RT_SAMPLE_SINGLE
};

static inline DWORD xr_rt_legacy_clear_mask(XrRtClearMask mask)
{
    switch (mask)
    {
    case XR_RT_CLEAR_COLOR: return D3DCLEAR_TARGET;
    default: NODEFAULT; return 0;
    }
}

static inline D3DMULTISAMPLE_TYPE xr_rt_legacy_sample_mode(XrRtSampleMode mode)
{
    switch (mode)
    {
    case XR_RT_SAMPLE_SINGLE: return D3DMULTISAMPLE_NONE;
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

    if "enum XrRtClearMask" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral depth/stencil compare vocabulary."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral compare block missing before state decoupling")
        close = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        close = text.find("\n", close) + 1
        text = text[:close] + STATE_BLOCK + text[close:]

    replacements = (
        ("D3DMULTISAMPLE_NONE, 0, TRUE, &rt_smap_ZB", "xr_rt_legacy_sample_mode(XR_RT_SAMPLE_SINGLE), 0, TRUE, &rt_smap_ZB"),
        ("D3DCLEAR_TARGET, 0x7f7f7f7f, 1.0f, 0L", "xr_rt_legacy_clear_mask(XR_RT_CLEAR_COLOR), 0x7f7f7f7f, 1.0f, 0L"),
    )
    applied = 0
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            applied += 1
        elif new not in text:
            raise RuntimeError(f"render-target state marker not found: {old}")

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("enum XrRtClearMask", "enum XrRtSampleMode", "xr_rt_legacy_clear_mask", "xr_rt_legacy_sample_mode"):
        if token not in final:
            raise RuntimeError(f"render-target state validation missing {token}")
    adapter_end = final.find("//////////////////////////////////////////////////////////////////////////", final.find("enum XrRtClearMask") + 1)
    body = final[adapter_end + len("//////////////////////////////////////////////////////////////////////////"):]
    for token in ("D3DCLEAR_TARGET", "D3DMULTISAMPLE_NONE"):
        if token in body:
            raise RuntimeError(f"direct D3D state token remains in render-target policy: {token}")
    print(f"[vulkan-rendertarget-state] centralized {applied} clear/sample state uses")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target clear and sample state.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
