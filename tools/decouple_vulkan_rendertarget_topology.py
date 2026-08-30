from __future__ import annotations

import argparse
from pathlib import Path

TOPOLOGY_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral primitive topology vocabulary. Transitional D3D9
// conversion remains centralized while Vulkan maps these to VkPrimitiveTopology.
enum XrPrimitiveTopology
{
    XR_PRIMITIVE_TRIANGLE_LIST,
    XR_PRIMITIVE_TRIANGLE_STRIP,
    XR_PRIMITIVE_LINE_LIST
};

static inline D3DPRIMITIVETYPE xr_primitive_legacy_topology(XrPrimitiveTopology topology)
{
    switch (topology)
    {
    case XR_PRIMITIVE_TRIANGLE_LIST: return D3DPT_TRIANGLELIST;
    case XR_PRIMITIVE_TRIANGLE_STRIP: return D3DPT_TRIANGLESTRIP;
    case XR_PRIMITIVE_LINE_LIST: return D3DPT_LINELIST;
    default: NODEFAULT; return D3DPT_TRIANGLELIST;
    }
}
//////////////////////////////////////////////////////////////////////////
'''

REPLACEMENTS = (
    ("RCache.Render(D3DPT_TRIANGLELIST,", "RCache.Render(xr_primitive_legacy_topology(XR_PRIMITIVE_TRIANGLE_LIST),"),
    ("RCache.Render(D3DPT_TRIANGLESTRIP,", "RCache.Render(xr_primitive_legacy_topology(XR_PRIMITIVE_TRIANGLE_STRIP),"),
    ("RCache.Render(D3DPT_LINELIST,", "RCache.Render(xr_primitive_legacy_topology(XR_PRIMITIVE_LINE_LIST),"),
)


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")
    if "enum XrPrimitiveTopology" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral render-target format vocabulary."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral format block missing before topology decoupling")
        end = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        end = text.find("\n", end) + 1
        text = text[:end] + TOPOLOGY_BLOCK + text[end:]

    applied = 0
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            applied += count
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    for token in ("enum XrPrimitiveTopology", "XR_PRIMITIVE_TRIANGLE_LIST", "xr_primitive_legacy_topology"):
        if token not in final:
            raise RuntimeError(f"render-target topology validation missing {token}")
    if applied == 0:
        raise RuntimeError("no render-target primitive topology uses were converted")
    print(f"[vulkan-rendertarget-topology] centralized {applied} primitive topology uses")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target primitive topology behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
