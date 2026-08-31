from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    header = root / "xr_3da" / "tss_def.h"
    source = root / "xr_3da" / "tss_def.cpp"
    if not header.is_file() or not source.is_file():
        raise FileNotFoundError("Vulkan cull-state hardening requires materialized tss_def sources")

    h = header.read_text(encoding="utf-8")
    if "XR_VK_RS_CULLMODE" not in h:
        old = "    XR_VK_RS_COLORWRITEENABLE = 1u << 7\n"
        new = "    XR_VK_RS_COLORWRITEENABLE = 1u << 7,\n    XR_VK_RS_CULLMODE = 1u << 8\n"
        if old not in h:
            raise RuntimeError("render-state cull: valid-bit marker missing")
        h = h.replace(old, new, 1)

    if "u32 cull_mode;" not in h:
        old = "    u32 color_write_enable;\n    u64 identity;"
        new = "    u32 color_write_enable;\n    u32 cull_mode;\n    u64 identity;"
        if old not in h:
            raise RuntimeError("render-state cull: snapshot field marker missing")
        h = h.replace(old, new, 1)
    header.write_text(h, encoding="utf-8")

    cpp = source.read_text(encoding="utf-8")
    if "case D3DRS_CULLMODE:" not in cpp:
        old = "        case D3DRS_COLORWRITEENABLE: bit = XR_VK_RS_COLORWRITEENABLE; target = &snapshot.color_write_enable; break;\n"
        new = old + "        case D3DRS_CULLMODE: bit = XR_VK_RS_CULLMODE; target = &snapshot.cull_mode; break;\n"
        if old not in cpp:
            raise RuntimeError("render-state cull: state capture marker missing")
        cpp = cpp.replace(old, new, 1)
    source.write_text(cpp, encoding="utf-8")

    final_h = header.read_text(encoding="utf-8")
    final_cpp = source.read_text(encoding="utf-8")
    for token in ("XR_VK_RS_CULLMODE = 1u << 8", "u32 cull_mode;"):
        if token not in final_h:
            raise RuntimeError(f"render-state cull validation failed: missing {token}")
    for token in ("case D3DRS_CULLMODE:", "target = &snapshot.cull_mode"):
        if token not in final_cpp:
            raise RuntimeError(f"render-state cull validation failed: missing {token}")

    print("[vulkan-render-state-cull] D3D9 cull mode captured into immutable pipeline snapshot")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extend SHOC Vulkan render-state snapshots with D3D9 cull mode.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
