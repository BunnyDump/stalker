from __future__ import annotations

import argparse
from pathlib import Path

from validate_vulkan_descriptor_snapshot_schema import validate as validate_vulkan_descriptor_snapshot_schema


GATE_CARDINALITY = '''        if (!vertex_constants || !pixel_constants || !pixel_textures || !vertex_textures ||
            pixel_texture_count != 16 || vertex_texture_count != 5)
            return false;
'''

GATE_RESOLUTION = GATE_CARDINALITY + '''
        xr_vk_resolved_texture_snapshot resolved_textures;
        if (!xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,
                vertex_textures, vertex_texture_count, resolved_textures))
            return false;
'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "struct xr_vk_resolved_texture_snapshot" not in text or "xr_vk_resolve_texture_snapshot" not in text:
        raise RuntimeError("Vulkan backend texture gate requires exact PS/VS texture snapshot resolution")
    if "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants" not in text:
        raise RuntimeError("Vulkan backend texture gate requires the exact CBackend resource snapshot ABI")

    proof = "xr_vk_resolved_texture_snapshot resolved_textures;"
    if proof not in text:
        count = text.count(GATE_CARDINALITY)
        if count != 1:
            raise RuntimeError(f"Vulkan backend texture gate cardinality marker count is {count}, expected 1")
        text = text.replace(GATE_CARDINALITY, GATE_RESOLUTION, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_resolved_texture_snapshot resolved_textures;",
        "xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,",
        "vertex_textures, vertex_texture_count, resolved_textures)",
        "pixel_texture_count != 16 || vertex_texture_count != 5",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend texture gate validation failed: missing {token}")

    gate_start = final.index("xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants")
    gate_end = final.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = final[gate_start:gate_end]
    resolve = gate.index("xr_vk_resolve_texture_snapshot")
    fail_closed = gate.rfind("return false;")
    if resolve >= fail_closed:
        raise RuntimeError("Vulkan backend texture gate opened or reordered before descriptor materialization")

    # At this integration point the descriptor schema, constant snapshot, texture snapshot and
    # production resource gate all exist. Validate them together so future helper changes cannot
    # silently desynchronize the shader ABI from the draw path.
    validate_vulkan_descriptor_snapshot_schema(root)

    print("[vulkan-backend-texture-gate] exact 16 PS + 5 VS Vulkan texture resolution + full descriptor snapshot ABI validated; draw remains fail-closed pending descriptor materialization")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the exact SHOC CBackend texture snapshot inside the production Vulkan resource gate.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
