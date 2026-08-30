from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def merge_tree(source: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    if not source.is_dir():
        return copied
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(relative.as_posix())
    return copied


def stage_runtime_closure(ready_root: Path) -> list[str]:
    """Copy the complete DLL closure produced by the isolated OpenAL vcpkg install."""
    bin_dir = ready_root / "bin"
    if not bin_dir.is_dir():
        raise FileNotFoundError(f"RC6 bin directory not found: {bin_dir}")

    temp_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
    candidates = (
        temp_root / "xray-rc6-vcpkg" / "installed-openal" / "x64-windows" / "bin",
        temp_root / "xray-rc6-vcpkg" / "installed-openal" / "x64-windows" / "debug" / "bin",
    )

    copied: list[str] = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        for dll in sorted(candidate.glob("*.dll")):
            shutil.copy2(dll, bin_dir / dll.name)
            copied.append(dll.name)

    if (bin_dir / "OpenAL32.dll").is_file() and not (bin_dir / "fmt.dll").is_file():
        searched = ", ".join(str(path) for path in candidates)
        raise RuntimeError(
            "OpenAL32.dll is present but fmt.dll was not staged; refusing to publish a broken bin. "
            f"Searched: {searched}"
        )

    return sorted(set(copied), key=str.lower)


def stage(workspace: Path, source_root: Path, ready_root: Path) -> None:
    workspace = workspace.resolve()
    source_root = source_root.resolve()
    ready_root = ready_root.resolve()
    if not ready_root.is_dir():
        raise FileNotFoundError(f"RC6 ready directory not found: {ready_root}")

    # Sparse-overlay policy: never copy source/full gamedata. The release may contain
    # only files explicitly placed under release/gamedata-overlay by this integration.
    gamedata = ready_root / "gamedata"
    if gamedata.exists():
        shutil.rmtree(gamedata)

    overlay = workspace / "release" / "gamedata-overlay"
    overlay_files: list[str] = []
    if overlay.is_dir():
        gamedata.mkdir(parents=True, exist_ok=True)
        overlay_files = merge_tree(overlay, gamedata)
        if not overlay_files:
            shutil.rmtree(gamedata)

    manifest = ready_root / "GAMEDATA_OVERLAY_MANIFEST.txt"
    lines = [
        "S.T.A.L.K.E.R. SHOC RC6 x64 Vulkan - sparse gamedata overlay",
        f"Integration commit: {os.environ.get('GITHUB_SHA', 'local')}",
        "Policy: only integration-modified gamedata files are shipped.",
        "Full/cumulative gamedata is forbidden.",
        f"Source root (intentionally not copied): {source_root}",
        "Files:",
    ]
    lines.extend(overlay_files if overlay_files else ["(none)"])
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    runtime_files = stage_runtime_closure(ready_root)
    (ready_root / "RUNTIME_DEPENDENCIES.txt").write_text(
        "OpenAL/vcpkg runtime DLL closure staged into bin:\n"
        + ("\n".join(runtime_files) if runtime_files else "(none)")
        + "\n",
        encoding="utf-8",
    )

    print(
        f"[release-stage] sparse gamedata files: {len(overlay_files)}; "
        f"OpenAL runtime DLLs: {len(runtime_files)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage sparse integration gamedata and the OpenAL runtime dependency closure."
    )
    parser.add_argument("source_pos", nargs="?")
    parser.add_argument("ready_pos", nargs="?")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source", dest="source_opt")
    parser.add_argument("--ready", dest="ready_opt")
    args = parser.parse_args()

    source = args.source_opt or args.source_pos or "source"
    ready = args.ready_opt or args.ready_pos or "READY_RC6_X64_VULKAN"
    stage(Path(args.workspace), Path(source), Path(ready))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
