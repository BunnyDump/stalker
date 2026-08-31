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

    gate_signature = "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants"
    if vk.count(gate_signature) != 1:
        raise RuntimeError("Vulkan resource gate is not uniquely snapshot-aware")
    if "pixel_texture_count != 16 || vertex_texture_count != 5" not in vk:
        raise RuntimeError("Vulkan resource gate does not verify SHOC PS/VS texture-slot cardinality")
    if vk.count("xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count") != 2:
        raise RuntimeError("indexed/non-indexed production draws do not both use the resource snapshot gate")

    # Safety invariant: until CTexture -> VkImage and constant-cache -> descriptor materialization
    # are implemented, the gate must remain fail-closed and the original D3D9 fallback must exist.
    gate_start = vk.index(gate_signature)
    gate_end = vk.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = vk[gate_start:gate_end]
    if "return false;" not in gate:
        raise RuntimeError("resource snapshot gate was opened before descriptor materialization became explicit")
    for token in ("DrawIndexedPrimitive", "DrawPrimitive"):
        if token not in runtime:
            raise RuntimeError(f"safe D3D9 fallback unexpectedly removed before full Vulkan resource migration: {token}")

    print("[validate-vulkan-backend-resources] production CBackend dispatch carries exact constant caches and all 21 texture slots; descriptor gate remains intentionally fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the SHOC CBackend -> Vulkan per-draw resource snapshot contract.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
