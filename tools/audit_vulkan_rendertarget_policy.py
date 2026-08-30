#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DELIM = "//////////////////////////////////////////////////////////////////////////"
ADAPTER_MARKERS = (
    "Renderer-neutral render-target format vocabulary.",
    "Renderer-neutral primitive topology vocabulary.",
    "Renderer-neutral vertex-layout vocabulary for render-target helper geometry.",
    "Renderer-neutral vertex declaration for helper passes.",
    "Renderer-neutral depth/stencil compare vocabulary.",
    "Renderer-neutral clear/sample vocabulary used by render-target policy.",
    "Legacy procedural texture upload adapter.",
    "Legacy render-surface lifetime adapter.",
)

MIGRATED_PATTERNS = {
    "format": re.compile(r"\b(?:D3DFORMAT|D3DFMT_[A-Z0-9_]+)\b"),
    "topology": re.compile(r"\bD3DPT_[A-Z0-9_]+\b"),
    "fvf": re.compile(r"\bD3DFVF_[A-Z0-9_]+\b"),
    "compare": re.compile(r"\bD3DCMP_[A-Z0-9_]+\b"),
    "clear_sample": re.compile(r"\b(?:D3DCLEAR_[A-Z0-9_]+|D3DMULTISAMPLE_[A-Z0-9_]+)\b"),
    "vertex_decl": re.compile(r"\b(?:D3DVERTEXELEMENT9|D3DDECL[A-Z0-9_]*)\b"),
}

REMAINING_PATTERNS = {
    "com_objects": re.compile(r"\bIDirect3D[A-Za-z0-9_]*\b"),
    "d3dx_helpers": re.compile(r"\bD3DX[A-Za-z0-9_]*\b"),
    "locked_types": re.compile(r"\bD3DLOCKED_[A-Z0-9_]+\b"),
    "pool_usage": re.compile(r"\b(?:D3DPOOL_[A-Z0-9_]+|D3DUSAGE_[A-Z0-9_]+)\b"),
    "device_calls": re.compile(r"\bHW\.pDevice\s*->"),
}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _mask_adapter_blocks(text: str) -> tuple[str, list[dict]]:
    chars = list(text)
    blocks: list[dict] = []
    for marker in ADAPTER_MARKERS:
        marker_pos = text.find(marker)
        if marker_pos < 0:
            raise RuntimeError(f"render-target adapter marker missing: {marker}")
        start = text.rfind(DELIM, 0, marker_pos)
        if start < 0:
            raise RuntimeError(f"adapter opening delimiter missing: {marker}")
        end = text.find(DELIM, marker_pos + len(marker))
        if end < 0:
            raise RuntimeError(f"adapter closing delimiter missing: {marker}")
        end += len(DELIM)
        blocks.append({"marker": marker, "start": start, "end": end})
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars), blocks


def _counts(text: str, patterns: dict[str, re.Pattern[str]]) -> dict[str, int]:
    return {name: len(pattern.findall(text)) for name, pattern in patterns.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit Direct3D leakage from renderer-neutral render-target policy.")
    ap.add_argument("source_root", type=Path)
    ap.add_argument("--json", dest="json_path", type=Path)
    args = ap.parse_args()

    source = args.source_root.resolve()
    path = source / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise SystemExit(f"render-target source missing: {path}")

    original = path.read_text(encoding="utf-8", errors="strict")
    masked, blocks = _mask_adapter_blocks(original)
    policy = _strip_comments(masked)
    adapters_only_chars = [" " if c != "\n" else "\n" for c in original]
    for block in blocks:
        for i in range(block["start"], block["end"]):
            adapters_only_chars[i] = original[i]
    adapters = _strip_comments("".join(adapters_only_chars))

    policy_migrated = _counts(policy, MIGRATED_PATTERNS)
    adapter_migrated = _counts(adapters, MIGRATED_PATTERNS)
    remaining = _counts(policy, REMAINING_PATTERNS)
    policy_total = sum(policy_migrated.values())

    report = {
        "file": str(path),
        "adapter_blocks": [block["marker"] for block in blocks],
        "migrated_policy_references": policy_migrated,
        "migrated_adapter_references": adapter_migrated,
        "remaining_unmigrated_policy_references": remaining,
        "migrated_policy_total": policy_total,
    }

    print("=== Vulkan render-target policy audit ===")
    print("migrated policy references:", policy_migrated)
    print("adapter references:", adapter_migrated)
    print("remaining ownership/resource coupling:", remaining)

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if policy_total:
        raise SystemExit(f"render-target policy audit failed: {policy_total} migrated Direct3D references remain outside adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
