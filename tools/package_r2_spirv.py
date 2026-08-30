from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def package(compile_dir: Path, gamedata_root: Path) -> dict:
    compile_dir = compile_dir.resolve()
    report_path = compile_dir / "spirv_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("failed", 1) != 0 or report.get("compiled") != report.get("total"):
        raise RuntimeError("SPIR-V package requires a strict zero-failure compilation report")

    binding_contract = report.get("binding_contract")
    if not binding_contract or binding_contract.get("ubo_binding") != 0 or binding_contract.get("sampled_binding_last") != 8:
        raise RuntimeError("SPIR-V package requires the normalized R2 descriptor binding contract")

    destination = gamedata_root.resolve() / "shaders" / "r2_vk"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    entries = []
    for row in report.get("results", []):
        if not row.get("success"):
            raise RuntimeError(f"Unexpected failed shader row: {row}")
        shader = Path(row["shader"])
        variant = row["variant"]
        source = compile_dir / "spirv" / shader.with_suffix(shader.suffix + f".{variant}.spv")
        if not source.is_file() or source.stat().st_size < 20:
            raise FileNotFoundError(source)
        relative = shader.with_suffix(shader.suffix + f".{variant}.spv")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append({
            "shader": row["shader"],
            "stage": row["stage"],
            "entrypoint": row["entrypoint"],
            "variant": variant,
            "defines": row.get("defines", []),
            "bindings": row.get("bindings", []),
            "path": relative.as_posix(),
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        })

    manifest = {
        "schema": 2,
        "format": "xray-r2-vulkan-spirv",
        "target_env": "vulkan1.0",
        "binding_contract": binding_contract,
        "source_corpus_files": report.get("corpus_files"),
        "entrypoint_files": report.get("entrypoint_files"),
        "shader_variants": len(entries),
        "coverage_percent": report.get("coverage_percent"),
        "entries": entries,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[vulkan-shader-package] packaged {len(entries)} normalized SPIR-V variants -> {destination}")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Package strict R2 SPIR-V compilation output into gamedata/shaders/r2_vk.")
    ap.add_argument("compile_dir", type=Path)
    ap.add_argument("gamedata_root", type=Path)
    args = ap.parse_args()
    package(args.compile_dir, args.gamedata_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
