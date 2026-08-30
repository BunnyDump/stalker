#!/usr/bin/env python3
"""Validate an RC6 x64/Vulkan distribution with sparse gamedata overlays."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from validate_windows_runtime_dependencies import validate_bin as validate_runtime_bin

IMAGE_FILE_MACHINE_AMD64 = 0x8664
REQUIRED_BINARIES = (
    "XR_3DA.exe",
    "xrCore.dll",
    "xrRender_VK.dll",
)


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


def parse_overlay_manifest(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    try:
        marker = lines.index("Files:")
    except ValueError as exc:
        raise ValueError("missing Files: section") from exc
    files = [line.strip().replace("\\", "/") for line in lines[marker + 1 :] if line.strip()]
    if files == ["(none)"]:
        return set()
    if "(none)" in files:
        raise ValueError("(none) cannot be mixed with file entries")
    return set(files)


def validate(root: Path) -> int:
    errors = 0
    bin_dir = root / "bin"
    gamedata_dir = root / "gamedata"
    overlay_manifest = root / "GAMEDATA_OVERLAY_MANIFEST.txt"

    if not bin_dir.is_dir():
        fail(f"missing bin directory: {bin_dir}")
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

    if bin_dir.is_dir():
        runtime_errors = validate_runtime_bin(bin_dir)
        for message in runtime_errors:
            fail(message)
        errors += len(runtime_errors)

    try:
        declared = parse_overlay_manifest(overlay_manifest)
    except (OSError, ValueError) as exc:
        fail(f"invalid sparse gamedata manifest: {exc}")
        declared = set()
        errors += 1

    actual: set[str] = set()
    if gamedata_dir.is_dir():
        actual = {
            path.relative_to(gamedata_dir).as_posix()
            for path in gamedata_dir.rglob("*")
            if path.is_file()
        }

    unexpected = sorted(actual - declared)
    missing = sorted(declared - actual)
    if unexpected:
        fail("gamedata contains files not declared as integration changes: " + ", ".join(unexpected))
        errors += 1
    if missing:
        fail("declared gamedata overlay files are missing: " + ", ".join(missing))
        errors += 1
    if not declared and gamedata_dir.exists() and not actual:
        fail("empty gamedata directory should not be shipped when no overlay files are changed")
        errors += 1

    print(f"sparse gamedata overlay files: {len(actual)}")

    if errors:
        fail(f"RC6 release validation failed with {errors} problem(s)")
        return 1

    print("RC6 release validation passed: x64 Vulkan engine + recursive runtime closure + sparse gamedata policy.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Root directory containing bin/ and optional sparse gamedata/")
    args = parser.parse_args()
    return validate(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
