#!/usr/bin/env python3
"""Audit the materialized xrRender_VK tree during the Vulkan migration.

The RC6 integration repository stores the engine as a reproducible upstream + patch
pipeline. This helper runs after that pipeline has materialized ``source`` and makes
remaining Direct3D coupling measurable instead of relying on directory names.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl",
    ".ps", ".vs", ".gs", ".hs", ".ds", ".cs", ".glsl", ".hlsl", ".txt",
    ".vcxproj", ".props", ".targets",
}

D3D_PATTERNS = {
    "d3d9": re.compile(r"\b(?:IDirect3D|D3D9|d3d9\.h|d3d9\.lib)\b", re.I),
    "d3d10": re.compile(r"\b(?:ID3D10|D3D10_|d3d10\.h|d3d10\.lib)\b", re.I),
    "d3d11": re.compile(r"\b(?:ID3D11|D3D11_|d3d11\.h|d3d11\.lib)\b", re.I),
    "dxgi": re.compile(r"\b(?:IDXGI|DXGI_|dxgi\.h|dxgi\.lib)\b", re.I),
    "d3dcompiler": re.compile(r"\b(?:D3DCompile|D3DReflect|d3dcompiler(?:_\d+)?\.lib)\b", re.I),
}

VULKAN_PATTERN = re.compile(
    r"\b(?:Vk[A-Z][A-Za-z0-9_]*|vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+|vulkan[\\/ ]vulkan\.h|vulkan-1\.lib)\b"
)


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path, help="Materialized engine source directory")
    parser.add_argument("--json", dest="json_path", type=Path, help="Optional JSON report path")
    parser.add_argument("--top", type=int, default=30, help="Maximum hotspot files to print")
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    renderer = source_root / "xr_3da" / "xrRender_VK"
    if not renderer.is_dir():
        raise SystemExit(f"xrRender_VK not found: {renderer}")

    counters = Counter()
    hotspots: list[dict[str, object]] = []
    files_scanned = 0
    vulkan_files = 0
    d3d_files = 0

    for path in iter_text_files(renderer):
        files_scanned += 1
        text = read_text(path)
        if not text:
            continue

        per_file = Counter()
        for name, pattern in D3D_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                per_file[name] = len(matches)
                counters[name] += len(matches)

        vk_count = len(VULKAN_PATTERN.findall(text))
        if vk_count:
            vulkan_files += 1
            counters["vulkan"] += vk_count

        if per_file:
            d3d_files += 1
            hotspots.append(
                {
                    "file": rel(path, renderer),
                    "d3d_references": sum(per_file.values()),
                    "categories": dict(per_file),
                    "vulkan_references": vk_count,
                }
            )

    hotspots.sort(key=lambda row: (-int(row["d3d_references"]), str(row["file"])))

    vcxproj = renderer / "xrRender_VK.vcxproj"
    project_text = read_text(vcxproj) if vcxproj.exists() else ""
    project_has_vulkan = bool(VULKAN_PATTERN.search(project_text))
    project_d3d = {
        name: len(pattern.findall(project_text)) for name, pattern in D3D_PATTERNS.items()
    }

    report = {
        "renderer": str(renderer),
        "files_scanned": files_scanned,
        "files_with_vulkan_references": vulkan_files,
        "files_with_direct3d_references": d3d_files,
        "reference_totals": dict(counters),
        "project_file": {
            "exists": vcxproj.exists(),
            "has_vulkan_reference": project_has_vulkan,
            "direct3d_references": project_d3d,
        },
        "hotspots": hotspots,
    }

    print("=== X-Ray xrRender_VK migration audit ===")
    print(f"Renderer: {renderer}")
    print(f"Text files scanned: {files_scanned}")
    print(f"Files containing Vulkan API tokens: {vulkan_files}")
    print(f"Files still containing Direct3D/DXGI tokens: {d3d_files}")
    print(f"Vulkan token count: {counters.get('vulkan', 0)}")
    for name in D3D_PATTERNS:
        print(f"{name} token count: {counters.get(name, 0)}")

    if hotspots:
        print("\nTop Direct3D coupling hotspots:")
        for row in hotspots[: max(args.top, 0)]:
            categories = ", ".join(f"{k}={v}" for k, v in row["categories"].items())
            print(f"  {row['file']}: {row['d3d_references']} ({categories}), vk={row['vulkan_references']}")
    else:
        print("\nNo Direct3D/DXGI tokens detected in xrRender_VK.")

    if not project_has_vulkan:
        print("\nWARNING: xrRender_VK.vcxproj does not currently expose a Vulkan header/library token.")

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON report: {args.json_path}")

    # This is an audit, not a gate: legacy coupling is expected during migration.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
