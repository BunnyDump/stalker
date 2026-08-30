#!/usr/bin/env python3
"""Validate a complete RC6 x64/Vulkan distribution (engine + gamedata)."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

IMAGE_FILE_MACHINE_AMD64 = 0x8664
REQUIRED_BINARIES = (
    "XR_3DA.exe",
    "xrCore.dll",
    "xrRender_VK.dll",
)
REQUIRED_GAMEDATA_DIRS = (
    "config",
    "textures",
)
MIN_GAMEDATA_FILES = 100


def pe_machine(path: Path) -> int:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("missing MZ header")
        stream.seek(0x3C)
        raw = stream.read(4)
        if len(raw) != 4:
            raise ValueError("truncated DOS header")
        pe_offset = struct.unpack("<I", raw)[0]
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError("missing PE signature")
        raw = stream.read(2)
        if len(raw) != 2:
            raise ValueError("truncated COFF header")
        return struct.unpack("<H", raw)[0]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def validate(root: Path) -> int:
    errors = 0
    bin_dir = root / "bin"
    gamedata_dir = root / "gamedata"

    if not bin_dir.is_dir():
        fail(f"missing bin directory: {bin_dir}")
        errors += 1
    if not gamedata_dir.is_dir():
        fail(f"missing gamedata directory: {gamedata_dir}")
        errors += 1

    for name in REQUIRED_BINARIES:
        path = bin_dir / name
        if not path.is_file():
            fail(f"missing required x64 binary: {path}")
            errors += 1
            continue
        try:
            machine = pe_machine(path)
        except (OSError, ValueError) as exc:
            fail(f"cannot validate {path}: {exc}")
            errors += 1
            continue
        if machine != IMAGE_FILE_MACHINE_AMD64:
            fail(f"{path} is not AMD64 (PE machine 0x{machine:04X})")
            errors += 1
        else:
            print(f"OK: {name} is AMD64")

    for name in REQUIRED_GAMEDATA_DIRS:
        path = gamedata_dir / name
        if not path.is_dir():
            fail(f"missing required gamedata directory: {path}")
            errors += 1

    if gamedata_dir.is_dir():
        gamedata_files = sum(1 for path in gamedata_dir.rglob("*") if path.is_file())
        print(f"gamedata files: {gamedata_files}")
        if gamedata_files < MIN_GAMEDATA_FILES:
            fail(
                f"gamedata is suspiciously incomplete: {gamedata_files} files "
                f"(< {MIN_GAMEDATA_FILES})"
            )
            errors += 1

    if errors:
        fail(f"RC6 release validation failed with {errors} problem(s)")
        return 1

    print("RC6 release validation passed: x64 engine + Vulkan renderer + gamedata present.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Root directory containing bin/ and gamedata/")
    args = parser.parse_args()
    return validate(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
