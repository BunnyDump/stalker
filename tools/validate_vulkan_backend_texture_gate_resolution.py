from __future__ import annotations

import argparse
from pathlib import Path

from validate_vulkan_backend_descriptor_materialization import validate as validate_descriptor_materialization


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    gate_signature = "xr_vk_backend_draw_resources_ready(VkPipeline pipeline"
    if text.count(gate_signature) != 1:
        raise RuntimeError("Vulkan backend texture gate is not uniquely pipeline/snapshot-aware")

    gate_start = text.index(gate_signature)
    gate_end = text.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = text[gate_start:gate_end]

    required = (
        "pixel_texture_count != 16 || vertex_texture_count != 5",
        "xr_vk_resolved_texture_snapshot resolved_textures;",
        "xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,",
        "vertex_textures, vertex_texture_count, resolved_textures)",
        "xr_vk_find_pipeline_texture_usage(pipeline, pixel_usage_mask, vertex_usage_mask)",
        "pixel_usage_mask & (1u << i)",
        "vertex_usage_mask & (1u << i)",
        "xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range)",
        "xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range",
        "return descriptor_set != VK_NULL_HANDLE;",
    )
    for token in required:
        if token not in gate:
            raise RuntimeError(f"Vulkan backend texture/descriptor gate missing: {token}")

    ordered = (
        "pixel_texture_count != 16 || vertex_texture_count != 5",
        "xr_vk_resolved_texture_snapshot resolved_textures;",
        "xr_vk_resolve_texture_snapshot",
        "xr_vk_find_pipeline_texture_usage",
        "pixel_usage_mask & (1u << i)",
        "vertex_usage_mask & (1u << i)",
        "xr_vk_upload_constant_snapshot",
        "xr_vk_allocate_snapshot_descriptor",
        "return descriptor_set != VK_NULL_HANDLE;",
    )
    positions = [gate.index(token) for token in ordered]
    if positions != sorted(positions):
        raise RuntimeError("Vulkan backend texture/descriptor gate ordering is unsafe")

    if "if (!resolved_textures.pixel[i])" in gate or "if (!resolved_textures.vertex[i])" in gate:
        raise RuntimeError("Vulkan backend texture gate still rejects statically-unused sparse slots")
    if "This gate is deliberately fail-closed" in gate:
        raise RuntimeError("Vulkan backend texture gate still contains the pre-materialization fail-closed path")

    validate_descriptor_materialization(root)
    print("[validate-vulkan-backend-texture-gate] exact texture resolution + SPIR-V usage masks feed live per-draw descriptors")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline-aware Vulkan texture resolution and descriptor materialization.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
