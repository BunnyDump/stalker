from __future__ import annotations

import argparse
from pathlib import Path

from enable_vulkan_static_geometry_mirror import install as install_vulkan_static_geometry_mirror
from harden_vulkan_static_geometry_lifecycle import harden as harden_vulkan_static_geometry_lifecycle
from harden_vulkan_backend_static_draw import harden as harden_vulkan_backend_static_draw


def harden(root: Path) -> None:
    # Keep static level/model migration tied to the resource gate that already sits in the
    # central capability pipeline. This avoids a second top-level integration point and
    # guarantees static draws are never introduced without the same fail-closed policy.
    install_vulkan_static_geometry_mirror(root)
    harden_vulkan_static_geometry_lifecycle(root)
    harden_vulkan_backend_static_draw(root)

    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    helper_marker = "    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
    helper = r'''    bool xr_vk_backend_draw_resources_ready()
    {
        // Production Vulkan draws must not bypass SHOC's active textures/constants.
        // This gate is deliberately fail-closed until the CBackend resource snapshot is
        // mirrored into Vulkan descriptors/uniforms for the exact current draw.
        return false;
    }

'''
    if "bool xr_vk_backend_draw_resources_ready()" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan backend resource gate: dynamic draw helper marker missing")
        text = text.replace(helper_marker, helper + helper_marker, 1)

    replacements = (
        (
            '''    if (xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;''',
            '''    if (xr_vk_backend_draw_resources_ready() &&
        xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;''',
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_indexed_backend_draw",
        ),
        (
            '''    if (xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;''',
            '''    if (xr_vk_backend_draw_resources_ready() &&
        xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;''',
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_backend_draw",
        ),
        (
            '''    if (xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;''',
            '''    if (xr_vk_backend_draw_resources_ready() &&
        xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;''',
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_indexed_backend_draw",
        ),
        (
            '''    if (xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;''',
            '''    if (xr_vk_backend_draw_resources_ready() &&
        xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;''',
            "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_backend_draw",
        ),
    )
    for original, guarded, proof in replacements:
        if proof in text:
            continue
        if original not in text:
            raise RuntimeError(f"Vulkan backend resource gate: live draw marker missing: {proof}")
        text = text.replace(original, guarded, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    for token in (
        "bool xr_vk_backend_draw_resources_ready()",
        "return false;",
        "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_indexed_backend_draw",
        "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_backend_draw",
        "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_indexed_backend_draw",
        "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_static_backend_draw",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan backend resource gate validation failed: missing {token}")

    print("[vulkan-backend-resource-gate] dynamic + static production draws fail closed until exact SHOC texture/constant descriptors are mirrored")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prevent live Vulkan backend draws before SHOC textures/constants are mirrored.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
