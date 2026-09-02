from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "u64 g_render_pass_generation = 0;",
        "struct xr_vk_pipeline_record",
        "record.render_pass_generation = g_render_pass_generation;",
        "bool xr_vk_pipeline_is_current(VkPipeline pipeline)",
        "void xr_vk_destroy_pipeline_handle(VkPipeline& pipeline)",
        "void xr_vk_destroy_stale_graphics_pipelines()",
        "void xr_vk_destroy_all_graphics_pipelines()",
        "++g_render_pass_generation;",
        "xr_vk_register_graphics_pipeline(pipeline);",
        "!xr_vk_pipeline_is_current(draw.pipeline)",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan pipeline generation validation failed: missing {token}")

    create_rp = text.index("g_vkCreateRenderPass(g_device, &render_pass_info, NULL, &g_render_pass)")
    bump = text.index("++g_render_pass_generation;", create_rp)
    framebuffer = text.index("g_framebuffers.assign", bump)
    if not create_rp < bump < framebuffer:
        raise RuntimeError("Vulkan pipeline generation validation failed: render-pass generation bump is misplaced")

    pipeline_create = text.index("g_vkCreateGraphicsPipelines(g_device")
    register = text.index("xr_vk_register_graphics_pipeline(pipeline);", pipeline_create)
    if register < pipeline_create:
        raise RuntimeError("Vulkan pipeline generation validation failed: pipeline registered before successful creation")

    draw_start = text.index("bool xr_vk_record_indexed_draw")
    draw_end = text.index("bool xr_vk_make_indexed_draw_packet", draw_start)
    draw = text[draw_start:draw_end]
    generation_guard = draw.index("!xr_vk_pipeline_is_current(draw.pipeline)")
    bind = draw.index("g_vkCmdBindPipeline(command_buffer")
    if generation_guard > bind:
        raise RuntimeError("Vulkan pipeline generation validation failed: stale pipeline can be bound")

    partial_start = text.index("void xr_vk_destroy_swapchain_resources()")
    full_start = text.index("void xr_vk_destroy_frame_resources()", partial_start)
    partial = text[partial_start:full_start]
    idle = partial.index("g_vkDeviceWaitIdle")
    stale_cleanup = partial.index("xr_vk_destroy_stale_graphics_pipelines();")
    if idle > stale_cleanup:
        raise RuntimeError("Vulkan pipeline generation validation failed: stale pipeline cleanup precedes GPU idle")
    if "xr_vk_destroy_all_graphics_pipelines();" in partial:
        raise RuntimeError("Vulkan pipeline generation validation failed: swapchain teardown destroys current-generation pipelines")

    window_start = text.index("void xr_vk_destroy_window_runtime()", full_start)
    full = text[full_start:window_start]
    destroy_all = full.index("xr_vk_destroy_all_graphics_pipelines();")
    cache_destroy = full.index("g_vkDestroyPipelineCache", destroy_all)
    if destroy_all > cache_destroy:
        raise RuntimeError("Vulkan pipeline generation validation failed: pipeline cache is destroyed before pipelines")

    print("[vulkan-pipeline-generation-validator] render-pass ownership and stale pipeline guards passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vulkan graphics pipeline render-pass generation ownership.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
