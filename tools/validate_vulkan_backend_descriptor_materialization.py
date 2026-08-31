from __future__ import annotations

import argparse
from pathlib import Path


UNIFORM_FRAME_CAPACITY = 64 * 1024 * 1024


def validate(root: Path) -> None:
    root = Path(root).resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    backend = root / "xr_3da" / "R_Backend_Runtime.h"
    for path in (source, backend):
        if not path.is_file():
            raise FileNotFoundError(path)

    text = source.read_text(encoding="utf-8")
    runtime = backend.read_text(encoding="utf-8")

    required = (
        f"const VkDeviceSize g_uniform_frame_capacity = {UNIFORM_FRAME_CAPACITY}",
        f"xr_vk_create_buffer({UNIFORM_FRAME_CAPACITY}ull, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT",
        "g_frame_descriptor_sets.push_back(descriptor_set)",
        "bool xr_vk_release_frame_descriptors()",
        "g_vkFreeDescriptorSets(g_device, g_descriptor_pool, count, &g_frame_descriptor_sets[0])",
        "VkDescriptorSet& descriptor_set",
        "descriptor_set = VK_NULL_HANDLE;",
        "xr_vk_resolved_texture_snapshot resolved_textures;",
        "xr_vk_backend_draw_resources_ready(VkPipeline pipeline",
        "xr_vk_find_pipeline_texture_usage(pipeline, pixel_usage_mask, vertex_usage_mask)",
        "pixel_usage_mask & (1u << i)",
        "vertex_usage_mask & (1u << i)",
        "xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range)",
        "xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range",
        "return descriptor_set != VK_NULL_HANDLE;",
        "VkDescriptorSet descriptor_set = VK_NULL_HANDLE;",
        "xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive",
        "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan backend descriptor validation failed: missing {token}")

    gate_signature = "xr_vk_backend_draw_resources_ready(VkPipeline pipeline"
    if text.count(gate_signature) != 1:
        raise RuntimeError("Vulkan backend descriptor validation failed: pipeline-aware resource gate is not unique")
    gate_start = text.index(gate_signature)
    gate_end = text.index("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = text[gate_start:gate_end]
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
    positions = [gate.find(token) for token in ordered]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise RuntimeError("Vulkan backend descriptor validation failed: resolve/usage-mask/upload/descriptor gate order is unsafe")

    if "if (!resolved_textures.pixel[i])" in gate or "if (!resolved_textures.vertex[i])" in gate:
        raise RuntimeError("Vulkan backend descriptor validation failed: obsolete all-slot sparse rejection remains")

    begin_start = text.index("bool xr_vk_bootstrap_begin_frame()")
    end_start = text.index("bool xr_vk_bootstrap_end_frame()", begin_start)
    begin = text[begin_start:end_start]
    wait = begin.find("g_vkWaitForFences")
    release = begin.find("xr_vk_release_frame_descriptors()", wait)
    reset_uniform = begin.find("xr_vk_reset_uniform_stream();", release)
    acquire = begin.find("g_vkAcquireNextImageKHR", reset_uniform)
    if min(wait, release, reset_uniform, acquire) < 0 or not wait < release < reset_uniform < acquire:
        raise RuntimeError("Vulkan backend descriptor validation failed: split-frame descriptor retirement is not fence-safe")

    for helper_name, draw_token in (
        ("bool xr_vk_record_dynamic_backend_draw", "g_vkCmdDraw(command_buffer, vertex_count"),
        ("bool xr_vk_record_static_indexed_backend_draw", "g_vkCmdDrawIndexed(command_buffer, index_count"),
        ("bool xr_vk_record_static_backend_draw", "g_vkCmdDraw(command_buffer, vertex_count"),
    ):
        start = text.index(helper_name)
        end_candidates = [
            pos for pos in (
                text.find("\n    bool ", start + len(helper_name)),
                text.find("\n    extern \"C\"", start + len(helper_name)),
            ) if pos >= 0
        ]
        end = min(end_candidates) if end_candidates else len(text)
        block = text[start:end]
        bind_pipeline = block.find("g_vkCmdBindPipeline")
        bind_descriptor = block.find("xr_vk_bind_material_descriptor", bind_pipeline)
        draw = block.find(draw_token, bind_descriptor)
        if min(bind_pipeline, bind_descriptor, draw) < 0 or not bind_pipeline < bind_descriptor < draw:
            raise RuntimeError(f"Vulkan backend descriptor validation failed: bind order invalid in {helper_name}")

    record_start = text.index("bool xr_vk_record_indexed_draw")
    record_end = text.index("bool xr_vk_make_indexed_draw_packet", record_start)
    record = text[record_start:record_end]
    pipeline_bind = record.find("g_vkCmdBindPipeline")
    descriptor_bind = record.find("xr_vk_bind_material_descriptor", pipeline_bind)
    indexed_draw = record.find("g_vkCmdDrawIndexed", descriptor_bind)
    if min(pipeline_bind, descriptor_bind, indexed_draw) < 0 or not pipeline_bind < descriptor_bind < indexed_draw:
        raise RuntimeError("Vulkan backend descriptor validation failed: indexed packet bind order invalid")

    if text.count("xr_vk_backend_draw_resources_ready(pipeline, vertex_constants, pixel_constants, pixel_textures, pixel_texture_count") != 2:
        raise RuntimeError("Vulkan backend descriptor validation failed: descriptor snapshot should materialize once per export")
    if text.count("if (descriptor_set != VK_NULL_HANDLE &&") < 2:
        raise RuntimeError("Vulkan backend descriptor validation failed: dynamic-to-static descriptor reuse missing")

    for token in (
        "HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC)",
        "HW.pDevice->DrawPrimitive(T, startV, PC)",
    ):
        if token not in runtime:
            raise RuntimeError(f"Vulkan backend descriptor validation failed: D3D9 fallback removed: {token}")

    print("[validate-vulkan-backend-descriptors] 64 MiB arena + fence-safe descriptors + SPIR-V static-usage sparse gate + D3D9 fallback verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live SHOC CBackend descriptor materialization for RC6 Vulkan.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
