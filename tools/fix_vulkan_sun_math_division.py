from __future__ import annotations

import argparse
from pathlib import Path


def fix(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_R_sun.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    needle = "    XrSunVec3 operator*(float s) const { return XrSunVec3(x * s, y * s, z * s); }\n"
    replacement = needle + "    XrSunVec3 operator/(float s) const { const float inv = 1.f / s; return XrSunVec3(x * inv, y * inv, z * inv); }\n"
    if "XrSunVec3 operator/(float s)" not in text:
        if needle not in text:
            raise RuntimeError("sun math division insertion marker not found")
        text = text.replace(needle, replacement, 1)
        source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    if "XrSunVec3 operator/(float s)" not in final:
        raise RuntimeError("sun math division operator missing")
    print("[vulkan-sun-math] scalar division operator installed")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add scalar division support to generated renderer-neutral sun vector math.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    fix(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
