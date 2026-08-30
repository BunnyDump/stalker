from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from prepare_r2_hlsl_for_spirv import preprocess_file


def compiler_command(compiler: Path, src: Path, out: Path, include_dir: Path, stage: str) -> list[str]:
    return [
        str(compiler),
        "-D",
        "-V",
        "--target-env", "vulkan1.0",
        "--auto-map-bindings",
        "--auto-map-locations",
        "-e", "main",
        "-S", stage,
        f"-I{include_dir}",
        "-o", str(out),
        str(src),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile legacy X-Ray R2 HLSL shaders to SPIR-V and emit a coverage report.")
    ap.add_argument("shader_root", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--compiler", type=Path, default=Path("glslangValidator.exe"))
    ap.add_argument("--allow-failures", action="store_true")
    args = ap.parse_args()

    root = args.shader_root.resolve()
    work = args.output.resolve()
    prepared = work / "prepared"
    spirv = work / "spirv"
    logs = work / "logs"
    for p in (prepared, spirv, logs):
        p.mkdir(parents=True, exist_ok=True)

    shaders = sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".vs", ".ps"}])
    if not shaders:
        raise SystemExit(f"No R2 .vs/.ps shaders found under {root}")

    results = []
    failures = []
    for src in shaders:
        rel = src.relative_to(root)
        prep = prepared / rel
        preprocess_file(src, prep)
        stage = "vert" if src.suffix.lower() == ".vs" else "frag"
        out = spirv / rel.with_suffix(rel.suffix + ".spv")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = compiler_command(args.compiler, prep, out, prepared, stage)
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = logs / rel.with_suffix(rel.suffix + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.stdout, encoding="utf-8", errors="replace")
        row = {
            "shader": rel.as_posix(),
            "stage": stage,
            "success": proc.returncode == 0 and out.is_file() and out.stat().st_size >= 20,
            "spirv_bytes": out.stat().st_size if out.is_file() else 0,
            "log": log.relative_to(work).as_posix(),
        }
        results.append(row)
        if not row["success"]:
            failures.append(row)

    report = {
        "shader_root": str(root),
        "total": len(results),
        "compiled": len(results) - len(failures),
        "failed": len(failures),
        "coverage_percent": round((len(results) - len(failures)) * 100.0 / len(results), 2),
        "results": results,
    }
    (work / "spirv_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"R2 SPIR-V coverage: {report['compiled']}/{report['total']} ({report['coverage_percent']}%)")
    if failures:
        first = failures[0]
        print(f"FIRST_R2_SPIRV_FAILURE: {first['shader']} -> {first['log']}")
        first_log = work / first["log"]
        if first_log.is_file():
            print(first_log.read_text(encoding="utf-8", errors="replace")[:6000])
        if not args.allow_failures:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
