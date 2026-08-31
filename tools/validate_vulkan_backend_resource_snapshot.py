from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    backend_h = root / "xr_3da" / "R_Backend.h"
    backend_runtime = root / "xr_3da" / "R_Backend_Runtime.h"
    vk_source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (backend_h, backend_runtime, vk_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    header = backend_h.read_text(encoding="utf-8")
    runtime = backend_runtime.read_text(encoding="utf-8")
    vk = vk_source.read_text(encoding="utf-8")

    header_tokens = (
        "const R_constant_array* vertex_constants",
        "const R_constant_array* pixel_constants",
        "CTexture* const* pixel_textures, u32 pixel_texture_count",
        "CTexture* const* vertex_textures, u32 vertex_texture_count",
    )
    for token in header_tokens:
        if header.count(token) < 2:
            raise RuntimeError(f"Vulkan backend resource snapshot ABI missing/partial: {token}")

    exact_snapshot = "&constants.a_vertex, &constants.a_pixel, textures_ps, 16, textures_vs, 5"
    if runtime.count(exact_snapshot) != 2:
        raise RuntimeError("CBackend Render overloads do not both forward the exact constant/texture snapshot")
    if "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV" in runtime:
        raise RuntimeError("legacy indexed Vulkan dispatch without resource snapshot remains")
    if "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV" in runtime:
        raise RuntimeError("legacy non-indexed Vulkan dispatch without resource snapshot remains")

    gate_signature = "xr_vk_backend_draw_resources_ready(VkPipeline pipeline"
    if vk.count(gate_signature) != 1:
        raise RuntimeError("Vulkan resource gate is not uniquely pipeline/snapshot-aware")
    if "pixel_texture_count != 16 || vertex_texture_count != 5" not in vk:
        raise RuntimeError("Vulkan resource gate does not verify SHOC PS/VS texture-slot cardinality")
    if vk.count("xr_vk_backend_draw_resources_ready(pipeline, vertex_constants, pixel_constants, pixel_textures, pixel_texture_count") != 2:
        raise RuntimeError("indexed/non-indexed production draws do not both materialize the exact resource snapshot")

    gate_start = vk.index(gate_signature)
    gate_end = vk.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = vk[gate_start:gate_end]
    ordered = (
        "xr_vk_resolve_texture_snapshot",
        "xr_vk_find_pipeline_texture_usage",
        "xr_vk_upload_constant_snapshot",
        "xr_vk_allocate_snapshot_descriptor",
        "return descriptor_set != VK_NULL_HANDLE;",
    )
    positions = [gate.find(token) for token in ordered]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise RuntimeError("Vulkan resource snapshot gate does not resolve textures, validate pipeline usage, upload constants and materialize descriptors in order")

    if "This gate is deliberately fail-closed" in gate:
        raise RuntimeError("stale fail-closed resource gate remains after descriptor materialization")
    for token in ("DrawIndexedPrimitive", "DrawPrimitive"):
        if token not in runtime:
            raise RuntimeError(f"safe D3D9 fallback unexpectedly removed during Vulkan resource migration: {token}")

    print("[validate-vulkan-backend-resources] exact constants + 21-slot snapshot + per-pipeline SPIR-V usage mask feed live descriptors with D3D9 fallback")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the SHOC CBackend -> Vulkan per-draw resource snapshot and usage-aware descriptor contract.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
