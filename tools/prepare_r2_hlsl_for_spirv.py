from __future__ import annotations

import argparse
import re
from pathlib import Path

TECHNIQUE_RE = re.compile(r"^\s*(?:FXVS|FXPS)\s*;?\s*$", re.MULTILINE)
INCLUDE_RE = re.compile(r'(^\s*#\s*include\s*[<\"])([^>\"]+)([>\"])', re.MULTILINE)


def preprocess_text(text: str) -> str:
    # X-Ray's legacy .vs/.ps files may terminate in FXVS/FXPS macros which expand
    # to D3D9 effect techniques. Vulkan consumes only the HLSL entry point.
    text = TECHNIQUE_RE.sub("", text)

    # Legacy R2 headers use Windows path separators inside #include strings.
    # glslang on Linux parses backslashes as string escapes, so normalize only
    # include paths while preserving shader source semantics.
    def normalize_include(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).replace("\\", "/") + match.group(3)

    return INCLUDE_RE.sub(normalize_include, text)


def preprocess_file(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8-sig", errors="strict")
    text = preprocess_text(text)
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
