from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    gate_signature = "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants"
    if text.count(gate_signature) != 1:
        raise RuntimeError("Vulkan backend texture gate is not uniquely snapshot-aware")

    gate_start = text.index(gate_signature)
    gate_end = text.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = text[gate_start:gate_end]

    required = (
        "pixel_texture_count != 16 || vertex_texture_count != 5",
        "xr_vk_resolved_texture_snapshot resolved_textures;",
        "xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,",
        "vertex_textures, vertex_texture_count, resolved_textures)",
    )
    for token in required:
        if token not in gate:
            raise RuntimeError(f"Vulkan backend texture gate resolution missing: {token}")

    cardinality = gate.index("pixel_texture_count != 16 || vertex_texture_count != 5")
    snapshot = gate.index("xr_vk_resolved_texture_snapshot resolved_textures;", cardinality)
    resolve = gate.index("xr_vk_resolve_texture_snapshot", snapshot)
    final_fail_closed = gate.rfind("return false;")
    if not cardinality < snapshot < resolve < final_fail_closed:
        raise RuntimeError("Vulkan backend texture gate resolution ordering is unsafe")

    if "return true;" in gate:
        raise RuntimeError("Vulkan backend texture gate opened before descriptor materialization")

    print("[validate-vulkan-backend-texture-gate] exact texture snapshot resolution is live inside the gate and still fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vulkan backend texture snapshot resolution and fail-closed ordering.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
