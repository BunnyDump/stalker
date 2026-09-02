from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants" not in text:
        raise RuntimeError("Vulkan static resource snapshot: resource-snapshot gate signature missing")

    replacements = (
        (
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_indexed_backend_draw",
            "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
            "            vertex_textures, vertex_texture_count) &&\n"
            "        xr_vk_record_static_indexed_backend_draw",
        ),
        (
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_backend_draw",
            "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
            "            vertex_textures, vertex_texture_count) &&\n"
            "        xr_vk_record_static_backend_draw",
        ),
    )
    for old, new in replacements:
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"Vulkan static resource snapshot: static gate marker missing: {old}")
        text = text.replace(old, new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    if "xr_vk_backend_draw_resources_ready()" in final:
        raise RuntimeError("Vulkan static resource snapshot: stale zero-argument resource gate call remains")
    for token in (
        "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_indexed_backend_draw",
        "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_backend_draw",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan static resource snapshot validation failed: missing {token}")

    print("[vulkan-static-resources] exact CBackend constant/texture snapshot now gates static level/model Vulkan draws too")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry exact SHOC CBackend resources into static Vulkan draw gating.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
