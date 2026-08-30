from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from normalize_spirv_bindings import normalize_bindings
from prepare_r2_hlsl_for_spirv import preprocess_tree

ENTRYPOINT_RE = re.compile(r"\b(main(?:_[A-Za-z0-9_]+)?)\s*\(")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"//[^\n]*")
SKIN_MACROS = ("SKIN_NONE", "SKIN_0", "SKIN_1", "SKIN_2")


def compiler_command(compiler: Path, src: Path, out: Path, include_dir: Path, stage: str, entrypoint: str, defines: tuple[str, ...]) -> list[str]:
    cmd = [
        str(compiler),
        "-D",
        "-V",
        "--target-env", "vulkan1.0",
        "--auto-map-bindings",
        "--auto-map-locations",
        "-e", entrypoint,
        "-S", stage,
        f"-I{include_dir}",
    ]
    cmd.extend(f"-D{name}=1" for name in defines)
    cmd.extend(["-o", str(out), str(src)])
    return cmd


def active_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = BLOCK_COMMENT_RE.sub("", text)
    text = LINE_COMMENT_RE.sub("", text)
    return text


def detect_entrypoint(path: Path) -> str | None:
    text = active_text(path)
    matches = ENTRYPOINT_RE.findall(text)
    if not matches:
        return None
    if "main" in matches:
        return "main"
    return matches[0]


def detect_variants(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    text = active_text(path)
    skins = [macro for macro in SKIN_MACROS if re.search(rf"\b{macro}\b", text)]
    if skins:
        return [(macro.lower(), (macro,)) for macro in skins]
    return [("default", tuple())]


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

    preprocess_tree(root, prepared)

    shaders = sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".vs", ".ps"}])
    if not shaders:
        raise SystemExit(f"No R2 .vs/.ps shaders found under {root}")

    results = []
    helpers = []
    failures = []
    entrypoint_files = 0
    for src in shaders:
        rel = src.relative_to(root)
        prep = prepared / rel
        stage = "vert" if src.suffix.lower() == ".vs" else "frag"
        entrypoint = detect_entrypoint(prep)
        if entrypoint is None:
            helpers.append({"shader": rel.as_posix(), "stage": stage, "classification": "helper/no-entrypoint"})
            continue
        entrypoint_files += 1

        for variant_name, defines in detect_variants(prep):
            out = spirv / rel.with_suffix(rel.suffix + f".{variant_name}.spv")
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = compiler_command(args.compiler, prep, out, prepared, stage, entrypoint, defines)
            proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log = logs / rel.with_suffix(rel.suffix + f".{variant_name}.log")
            log.parent.mkdir(parents=True, exist_ok=True)
            log_text = proc.stdout
            success = proc.returncode == 0 and out.is_file() and out.stat().st_size >= 20
            bindings = []
            if success:
                try:
                    bindings = normalize_bindings(out)
                except Exception as exc:
                    success = False
                    log_text += f"\nSPIR-V binding normalization failed: {exc}\n"
            log.write_text(log_text, encoding="utf-8", errors="replace")
            row = {
                "shader": rel.as_posix(),
                "stage": stage,
                "entrypoint": entrypoint,
                "variant": variant_name,
                "defines": list(defines),
                "bindings": bindings,
                "success": success,
                "spirv_bytes": out.stat().st_size if out.is_file() else 0,
                "log": log.relative_to(work).as_posix(),
            }
            results.append(row)
            if not row["success"]:
                failures.append(row)

    total = len(results)
    compiled = total - len(failures)
    report = {
        "shader_root": str(root),
        "corpus_files": len(shaders),
        "entrypoint_files": entrypoint_files,
        "helper_files": len(helpers),
        "helpers": helpers,
        "total": total,
        "compiled": compiled,
        "failed": len(failures),
        "coverage_percent": round(compiled * 100.0 / total, 2) if total else 0.0,
        "binding_contract": {
            "descriptor_set": 0,
            "ubo_binding": 0,
            "sampled_binding_first": 1,
            "sampled_binding_last": 8,
        },
        "results": results,
    }
    (work / "spirv_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"R2 SPIR-V variant coverage: {compiled}/{total} ({report['coverage_percent']}%); entrypoint_files={entrypoint_files} helpers={len(helpers)} corpus={len(shaders)}")
    if failures:
        first = failures[0]
        print(f"FIRST_R2_SPIRV_FAILURE: {first['shader']} [{first['entrypoint']}:{first['variant']}] -> {first['log']}")
        first_log = work / first["log"]
        if first_log.is_file():
            print(first_log.read_text(encoding="utf-8", errors="replace")[:6000])
        if not args.allow_failures:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
