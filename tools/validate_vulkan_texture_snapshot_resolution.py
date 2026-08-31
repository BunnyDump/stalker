from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "XR_VK_PIXEL_TEXTURE_SLOTS = 16",
        "XR_VK_VERTEX_TEXTURE_SLOTS = 5",
        "struct xr_vk_resolved_texture_snapshot",
        "const xr_vk_texture_resource* pixel[XR_VK_PIXEL_TEXTURE_SLOTS]",
        "const xr_vk_texture_resource* vertex[XR_VK_VERTEX_TEXTURE_SLOTS]",
        "bool xr_vk_resolve_texture_stage",
        "texture_count != expected_count",
        "resolved[index] = NULL;",
        "if (!textures[index])",
        "const xr_vk_texture_resource* resource = xr_vk_find_texture_resource(textures[index])",
        "if (!resource)",
        "bool xr_vk_resolve_texture_snapshot",
        "XR_VK_PIXEL_TEXTURE_SLOTS, snapshot.pixel",
        "XR_VK_VERTEX_TEXTURE_SLOTS, snapshot.vertex",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan texture snapshot validation failed: missing {token}")

    if text.count("struct xr_vk_resolved_texture_snapshot") != 1:
        raise RuntimeError("Vulkan texture snapshot validation failed: duplicate snapshot structure")
    if text.count("XR_VK_PIXEL_TEXTURE_SLOTS = 16") != 1:
        raise RuntimeError("Vulkan texture snapshot validation failed: duplicate PS slot contract")
    if text.count("XR_VK_VERTEX_TEXTURE_SLOTS = 5") != 1:
        raise RuntimeError("Vulkan texture snapshot validation failed: duplicate VS slot contract")

    stage_start = text.index("bool xr_vk_resolve_texture_stage")
    snapshot_start = text.index("bool xr_vk_resolve_texture_snapshot", stage_start)
    stage = text[stage_start:snapshot_start]
    count_guard = stage.index("texture_count != expected_count")
    clear_slot = stage.index("resolved[index] = NULL;", count_guard)
    null_slot = stage.index("if (!textures[index])", clear_slot)
    lookup = stage.index("xr_vk_find_texture_resource(textures[index])", null_slot)
    fail = stage.index("if (!resource)", lookup)
    assign = stage.index("resolved[index] = resource;", fail)
    if not count_guard < clear_slot < null_slot < lookup < fail < assign:
        raise RuntimeError("Vulkan texture snapshot validation failed: stage resolution ordering is unsafe")

    snapshot_end = text.index("bool xr_vk_texture_snapshot_resolved", snapshot_start)
    snapshot = text[snapshot_start:snapshot_end]
    reset = snapshot.index("snapshot = xr_vk_resolved_texture_snapshot();")
    ps = snapshot.index("XR_VK_PIXEL_TEXTURE_SLOTS, snapshot.pixel", reset)
    vs = snapshot.index("XR_VK_VERTEX_TEXTURE_SLOTS, snapshot.vertex", ps)
    if not reset < ps < vs:
        raise RuntimeError("Vulkan texture snapshot validation failed: PS/VS snapshot ordering is unstable")

    print("[validate-vulkan-texture-snapshot] exact 16 PS + 5 VS resolution contract verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exact SHOC PS/VS CTexture snapshot resolution for Vulkan.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
