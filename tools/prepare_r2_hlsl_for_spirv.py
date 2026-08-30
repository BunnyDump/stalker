from __future__ import annotations

import argparse
import re
from pathlib import Path

TECHNIQUE_RE = re.compile(r"^\s*(?:FXVS|FXPS)\s*;?\s*$", re.MULTILINE)
INCLUDE_RE = re.compile(r'(^\s*#\s*include\s*[<\"])([^>\"]+)([>\"])', re.MULTILINE)
RESERVED_POINT_RE = re.compile(r"\bpoint\b")
LOD_COMPAT = """#define tex2Dlod(s,c) tex2D(s,(c).xy)\n#define tex3Dlod(s,c) tex3D(s,(c).xyz)\n#define texCUBElod(s,c) texCUBE(s,(c).xyz)\n"""


def decode_legacy_shader(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def preprocess_text(text: str) -> str:
    text = TECHNIQUE_RE.sub("", text)

    def normalize_include(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).replace("\\", "/") + match.group(3)

    text = INCLUDE_RE.sub(normalize_include, text)
    text = RESERVED_POINT_RE.sub("xr_point", text)
    return text


def preprocess_file(src: Path, dst: Path) -> None:
    text = decode_legacy_shader(src.read_bytes())
    text = preprocess_text(text)
    if src.suffix.lower() in {".vs", ".ps"}:
        # glslang cannot lower several DX9 combined-sampler explicit-LOD
        # intrinsics. R2 uses these compatibility calls with zero LOD; map them
        # to the equivalent legacy sample using the spatial coordinate portion.
        text = LOD_COMPAT + text
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")


def preprocess_tree(source: Path, output: Path) -> None:
    for src in source.rglob("*"):
        if src.is_file() and src.suffix.lower() in {".vs", ".ps", ".h"}:
            preprocess_file(src, output / src.relative_to(source))


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare legacy X-Ray R2 HLSL sources for SPIR-V compilation.")
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    if args.source.is_dir():
        preprocess_tree(args.source, args.output)
    else:
        preprocess_file(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
