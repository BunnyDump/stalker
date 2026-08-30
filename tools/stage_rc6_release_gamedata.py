from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def merge_tree(source: Path, destination: Path) -> int:
    if not source.is_dir():
        return 0
    copied = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def stage(workspace: Path, source_root: Path, ready_root: Path) -> None:
    workspace = workspace.resolve()
    source_root = source_root.resolve()
    ready_root = ready_root.resolve()
    if not ready_root.is_dir():
        raise FileNotFoundError(f"RC6 ready directory not found: {ready_root}")

    gamedata = ready_root / "gamedata"
    gamedata.mkdir(parents=True, exist_ok=True)

    # Preserve any full gamedata tree carried by the source checkout/build, then overlay
    # integration-repository changes. This makes the release directory cumulative.
    source_candidates = (
        source_root / "gamedata",
        source_root / "_release" / "gamedata",
    )
    total = 0
    source_count = 0
    for candidate in source_candidates:
        copied = merge_tree(candidate, gamedata)
        source_count += copied
        total += copied

    overlay = workspace / "release" / "gamedata-overlay"
    overlay_count = merge_tree(overlay, gamedata)
    total += overlay_count

    marker = gamedata / "RC6_VULKAN_BUILD.txt"
    marker.write_text(
        "S.T.A.L.K.E.R. SHOC RC6 x64 Vulkan\n"
        "This gamedata directory is staged cumulatively by the integration pipeline.\n"
        f"Integration commit: {os.environ.get('GITHUB_SHA', 'local')}\n"
        "Pinned upstream: ac3c009a3ecea26b60f16468993e7c540d063acf\n"
        f"Source gamedata files staged: {source_count}\n"
        f"Integration overlay files staged: {overlay_count}\n",
        encoding="utf-8",
    )

    if not marker.is_file():
        raise RuntimeError("RC6 gamedata marker was not created")
    print(
        f"[release-gamedata] staged {total} resource files "
        f"({source_count} source + {overlay_count} integration overlays) into {gamedata}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage cumulative gamedata into the RC6 x64 Vulkan release artifact.")
    # Compatibility with both CI forms used by the integration workflows:
    #   stage_rc6_release_gamedata.py SOURCE READY
    #   stage_rc6_release_gamedata.py --workspace W --source SOURCE --ready READY
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
