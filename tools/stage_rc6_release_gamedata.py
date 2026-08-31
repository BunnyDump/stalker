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


def _copy_dlls(source: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    if not source.is_dir():
        return copied
    for dll in sorted(source.glob("*.dll"), key=lambda path: path.name.lower()):
        shutil.copy2(dll, destination / dll.name)
        copied.append(dll.name)
    return copied


def _find_vc_runtime_dir() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("VCToolsRedistDir")
    if explicit:
        root = Path(explicit)
        candidates.extend(
            (
                root / "x64" / "Microsoft.VC143.CRT",
                root / "x64" / "Microsoft.VC142.CRT",
            )
        )

    roots = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "2022",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Visual Studio" / "2022",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for edition in root.iterdir():
            redist = edition / "VC" / "Redist" / "MSVC"
            if not redist.is_dir():
                continue
            for version in redist.iterdir():
                candidates.extend(
                    (
                        version / "x64" / "Microsoft.VC143.CRT",
                        version / "x64" / "Microsoft.VC142.CRT",
                    )
                )

    existing = [path for path in candidates if path.is_dir()]
    if not existing:
        return None
    return sorted(existing, key=lambda path: str(path).lower())[-1]


def stage_runtime_closure(ready_root: Path) -> tuple[list[str], list[str]]:
    """Copy the self-contained OpenAL DLL and VC runtime needed by other RC6 binaries."""
    bin_dir = ready_root / "bin"
    if not bin_dir.is_dir():
        raise FileNotFoundError(f"RC6 bin directory not found: {bin_dir}")

    temp_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
    openal_candidates = (
        temp_root / "xray-rc6-vcpkg" / "installed-openal" / "xray-openal-static-crt" / "bin",
        temp_root / "xray-rc6-vcpkg" / "installed-openal" / "xray-openal-static-crt" / "debug" / "bin",
    )

    openal_files: list[str] = []
    for candidate in openal_candidates:
        openal_files.extend(_copy_dlls(candidate, bin_dir))

    if not (bin_dir / "OpenAL32.dll").is_file() and not (bin_dir / "openal32.dll").is_file():
        searched = ", ".join(str(path) for path in openal_candidates)
        raise RuntimeError(
            "Static-CRT OpenAL32.dll was not staged from the RC6 overlay port. "
            f"Searched: {searched}"
        )

    vc_files: list[str] = []
    vc_runtime = _find_vc_runtime_dir()
    if vc_runtime is not None:
        vc_files = _copy_dlls(vc_runtime, bin_dir)

    return (
        sorted(set(openal_files), key=str.lower),
        sorted(set(vc_files), key=str.lower),
    )


def stage_vulkan_launcher(ready_root: Path) -> Path:
    launcher = ready_root / "START_VULKAN.bat"
    launcher.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "pushd \"%~dp0\"\r\n"
        "if not exist \"bin\\XR_3DA.exe\" (\r\n"
        "  echo ERROR: bin\\XR_3DA.exe not found.\r\n"
        "  pause\r\n"
        "  exit /b 2\r\n"
        ")\r\n"
        "\"bin\\XR_3DA.exe\" -vulkan %*\r\n"
        "set rc=%ERRORLEVEL%\r\n"
        "popd\r\n"
        "exit /b %rc%\r\n",
        encoding="ascii",
        newline="",
    )
    return launcher


def stage(workspace: Path, source_root: Path, ready_root: Path) -> None:
    workspace = workspace.resolve()
    source_root = source_root.resolve()
    ready_root = ready_root.resolve()
    if not ready_root.is_dir():
        raise FileNotFoundError(f"RC6 ready directory not found: {ready_root}")

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

    openal_files, vc_files = stage_runtime_closure(ready_root)
    launcher = stage_vulkan_launcher(ready_root)
    runtime_lines = [
        "RC6 Windows runtime closure staged into bin:",
        "",
        "OpenAL overlay DLLs (bundled fmt + static CRT):",
        *(openal_files if openal_files else ["(none)"]),
        "",
        "Microsoft VC Redistributable DLLs for remaining engine modules:",
        *(vc_files if vc_files else ["(none)"]),
        "",
        f"Vulkan launcher: {launcher.name}",
        "Launch policy: START_VULKAN.bat passes -vulkan; engine falls back to R2/R1 if xrRender_VK.dll cannot load.",
    ]
    (ready_root / "RUNTIME_DEPENDENCIES.txt").write_text(
        "\n".join(runtime_lines) + "\n", encoding="utf-8"
    )

    print(
        f"[release-stage] sparse gamedata files: {len(overlay_files)}; "
        f"OpenAL overlay DLLs: {len(openal_files)}; VC runtime DLLs: {len(vc_files)}; "
        f"launcher: {launcher.name}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage sparse integration gamedata, Vulkan launcher and Windows runtime dependency closure."
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
