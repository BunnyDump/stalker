#!/usr/bin/env python3
"""Stage a complete RC6 release: x64/Vulkan bin + cumulative gamedata + SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

CANONICAL_GAMEDATA_V24_SHA256 = "ce0bc0845f888c6cf879e56e4ccfc0d37008e0d641ca1b1f9c560dc944e08f27"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive, "r") as zf:
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe path in gamedata archive: {member.filename}")
        zf.extractall(destination)


def locate_gamedata_root(extracted: Path) -> Path:
    direct = extracted / "gamedata"
    if direct.is_dir():
        return direct
    if (extracted / "config").is_dir() and (extracted / "textures").is_dir():
        return extracted
    candidates = [p for p in extracted.rglob("gamedata") if p.is_dir()]
    valid = [p for p in candidates if (p / "config").is_dir() and (p / "textures").is_dir()]
    if len(valid) != 1:
        raise RuntimeError(f"cannot uniquely locate gamedata root in {extracted}")
    return valid[0]


def stage_gamedata(source: Path, destination: Path, expected_archive_sha256: str | None) -> str | None:
    if source.is_dir():
        source_root = source / "gamedata" if (source / "gamedata").is_dir() else source
        copy_tree(source_root, destination)
        return None
    if not source.is_file() or source.suffix.lower() != ".zip":
        raise RuntimeError("--gamedata must point to a gamedata directory or .zip archive")

    archive_hash = sha256(source)
    if expected_archive_sha256 and archive_hash.lower() != expected_archive_sha256.lower():
        raise RuntimeError(
            f"gamedata archive SHA-256 mismatch: {archive_hash} != {expected_archive_sha256.lower()}"
        )

    temp = destination.parent / ".gamedata_extract"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    try:
        safe_extract_zip(source, temp)
        copy_tree(locate_gamedata_root(temp), destination)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return archive_hash


def write_manifest(root: Path) -> Path:
    manifest = root / "SHA256SUMS.txt"
    rows: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p != manifest):
        relative = path.relative_to(root).as_posix()
        rows.append(f"{sha256(path)}  {relative}")
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage a complete STALKER RC6 x64/Vulkan release.")
    parser.add_argument("--bin", type=Path, required=True, help="Directory containing built x64 engine binaries")
    parser.add_argument("--gamedata", type=Path, required=True, help="Cumulative gamedata directory or ZIP")
    parser.add_argument("--output", type=Path, required=True, help="Release staging directory")
    parser.add_argument(
        "--expected-gamedata-sha256",
        default=None,
        help="Expected SHA-256 when --gamedata is an archive; use 'v24' for the canonical v24 hash",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Do not run validate_rc6_release.py")
    args = parser.parse_args()

    bin_source = args.bin.resolve()
    gamedata_source = args.gamedata.resolve()
    output = args.output.resolve()
    expected = args.expected_gamedata_sha256
    if expected and expected.lower() == "v24":
        expected = CANONICAL_GAMEDATA_V24_SHA256

    if output.exists():
        shutil.rmtree(output)
    (output / "bin").mkdir(parents=True)
    (output / "gamedata").mkdir(parents=True)

    copy_tree(bin_source, output / "bin")
    archive_hash = stage_gamedata(gamedata_source, output / "gamedata", expected)
    manifest = write_manifest(output)

    metadata = output / "RC6_RELEASE_INFO.txt"
    metadata.write_text(
        "STALKER X-Ray RC6 x64/Vulkan\n"
        f"gamedata_source={gamedata_source.name}\n"
        f"gamedata_archive_sha256={archive_hash or 'directory-source'}\n"
        f"manifest={manifest.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    # Refresh manifest so release metadata is covered too.
    write_manifest(output)

    if not args.skip_validation:
        validator = Path(__file__).resolve().with_name("validate_rc6_release.py")
        result = subprocess.run([sys.executable, str(validator), str(output)], check=False)
        if result.returncode:
            return result.returncode

    print(f"RC6 release staged: {output}")
    print(f"SHA-256 manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
