from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkPipelineCache g_pipeline_cache = VK_NULL_HANDLE;\n"
    state_block = state_marker + r'''    u64 g_render_pass_generation = 0;

    struct xr_vk_pipeline_record
    {
        VkPipeline pipeline;
        u64 render_pass_generation;
    };

    xr_vector<xr_vk_pipeline_record> g_graphics_pipelines;
'''
    if "struct xr_vk_pipeline_record" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan pipeline generation: pipeline-cache state marker not found")
        text = text.replace(state_marker, state_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    void xr_vk_register_graphics_pipeline(VkPipeline pipeline)
    {
        if (pipeline == VK_NULL_HANDLE)
            return;
        xr_vk_pipeline_record record;
        record.pipeline = pipeline;
        record.render_pass_generation = g_render_pass_generation;
        g_graphics_pipelines.push_back(record);
    }

    bool xr_vk_pipeline_is_current(VkPipeline pipeline)
    {
        if (pipeline == VK_NULL_HANDLE)
            return false;
        for (u32 i = 0; i < g_graphics_pipelines.size(); ++i)
            if (g_graphics_pipelines[i].pipeline == pipeline)
                return g_graphics_pipelines[i].render_pass_generation == g_render_pass_generation;
        return false;
    }

    void xr_vk_destroy_pipeline_handle(VkPipeline& pipeline)
    {
        if (pipeline == VK_NULL_HANDLE)
            return;
        for (u32 i = 0; i < g_graphics_pipelines.size(); ++i)
        {
            if (g_graphics_pipelines[i].pipeline != pipeline)
                continue;
            if (g_device != VK_NULL_HANDLE && g_vkDestroyPipeline)
                g_vkDestroyPipeline(g_device, pipeline, NULL);
            g_graphics_pipelines.erase(g_graphics_pipelines.begin() + i);
            pipeline = VK_NULL_HANDLE;
            return;
        }
        pipeline = VK_NULL_HANDLE;
    }

    void xr_vk_destroy_stale_graphics_pipelines()
    {
        for (u32 i = 0; i < g_graphics_pipelines.size();)
        {
            if (g_graphics_pipelines[i].render_pass_generation == g_render_pass_generation)
            {
                ++i;
                continue;
            }
            if (g_device != VK_NULL_HANDLE && g_vkDestroyPipeline && g_graphics_pipelines[i].pipeline != VK_NULL_HANDLE)
                g_vkDestroyPipeline(g_device, g_graphics_pipelines[i].pipeline, NULL);
            g_graphics_pipelines.erase(g_graphics_pipelines.begin() + i);
        }
    }

    void xr_vk_destroy_all_graphics_pipelines()
    {
        if (g_device != VK_NULL_HANDLE && g_vkDestroyPipeline)
            for (u32 i = 0; i < g_graphics_pipelines.size(); ++i)
                if (g_graphics_pipelines[i].pipeline != VK_NULL_HANDLE)
                    g_vkDestroyPipeline(g_device, g_graphics_pipelines[i].pipeline, NULL);
        g_graphics_pipelines.clear();
    }

'''
    if "xr_vk_pipeline_is_current" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan pipeline generation: shader helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    create_renderpass = '''        if (g_vkCreateRenderPass(g_device, &render_pass_info, NULL, &g_render_pass) != VK_SUCCESS)
            return false;
'''
    create_renderpass_new = create_renderpass + '''        ++g_render_pass_generation;
        if (!g_render_pass_generation)
            ++g_render_pass_generation;
'''
    if "++g_render_pass_generation;" not in text:
        if create_renderpass not in text:
            raise RuntimeError("Vulkan pipeline generation: render-pass creation marker not found")
        text = text.replace(create_renderpass, create_renderpass_new, 1)

    pipeline_return = "        return result == VK_SUCCESS ? pipeline : VK_NULL_HANDLE;\n"
    pipeline_return_new = '''        if (result != VK_SUCCESS)
            return VK_NULL_HANDLE;
        xr_vk_register_graphics_pipeline(pipeline);
        return pipeline;
'''
    if "xr_vk_register_graphics_pipeline(pipeline);" not in text:
        if pipeline_return not in text:
            raise RuntimeError("Vulkan pipeline generation: graphics-pipeline return marker not found")
        text = text.replace(pipeline_return, pipeline_return_new, 1)

    indexed_guard = '''        if (command_buffer == VK_NULL_HANDLE || draw.pipeline == VK_NULL_HANDLE || !draw.index_count ||
            !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed)
            return false;
'''
    indexed_guard_new = '''        if (command_buffer == VK_NULL_HANDLE || draw.pipeline == VK_NULL_HANDLE || !draw.index_count ||
            !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed || !xr_vk_pipeline_is_current(draw.pipeline))
            return false;
'''
    if "!xr_vk_pipeline_is_current(draw.pipeline)" not in text:
        if indexed_guard not in text:
            raise RuntimeError("Vulkan pipeline generation: indexed-draw guard marker not found")
        text = text.replace(indexed_guard, indexed_guard_new, 1)

    partial_start = text.find("    void xr_vk_destroy_swapchain_resources()\n    {")
    full_start = text.find("    void xr_vk_destroy_frame_resources()\n    {", partial_start)
    if partial_start < 0 or full_start < 0:
        raise RuntimeError("Vulkan pipeline generation: resource teardown functions not found")
    partial = text[partial_start:full_start]
    idle_marker = '''        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);
'''
    stale_call = idle_marker + "        xr_vk_destroy_stale_graphics_pipelines();\n"
    if "xr_vk_destroy_stale_graphics_pipelines();" not in partial:
        if idle_marker not in partial:
            raise RuntimeError("Vulkan pipeline generation: swapchain idle marker not found")
        partial = partial.replace(idle_marker, stale_call, 1)
        text = text[:partial_start] + partial + text[full_start:]

    # Full shutdown must destroy every still-owned pipeline before the pipeline cache/layout/device disappear.
    full_start = text.find("    void xr_vk_destroy_frame_resources()\n    {")
    window_start = text.find("    void xr_vk_destroy_window_runtime()", full_start)
    full = text[full_start:window_start]
    if "xr_vk_destroy_all_graphics_pipelines();" not in full:
        cache_destroy = "            if (g_pipeline_cache != VK_NULL_HANDLE && g_vkDestroyPipelineCache) g_vkDestroyPipelineCache(g_device, g_pipeline_cache, NULL);\n"
        if cache_destroy not in full:
            raise RuntimeError("Vulkan pipeline generation: full-shutdown cache marker not found")
        full = full.replace(cache_destroy, "            xr_vk_destroy_all_graphics_pipelines();\n" + cache_destroy, 1)
        text = text[:full_start] + full + text[window_start:]

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "u64 g_render_pass_generation = 0;",
        "struct xr_vk_pipeline_record",
        "xr_vk_register_graphics_pipeline",
        "xr_vk_pipeline_is_current",
        "xr_vk_destroy_pipeline_handle",
        "xr_vk_destroy_stale_graphics_pipelines",
        "xr_vk_destroy_all_graphics_pipelines",
        "++g_render_pass_generation;",
        "xr_vk_register_graphics_pipeline(pipeline);",
        "!xr_vk_pipeline_is_current(draw.pipeline)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan pipeline generation validation failed: missing {token}")

    partial_start = final.index("void xr_vk_destroy_swapchain_resources()")
    full_start = final.index("void xr_vk_destroy_frame_resources()", partial_start)
    partial = final[partial_start:full_start]
    if "xr_vk_destroy_all_graphics_pipelines();" in partial:
        raise RuntimeError("Vulkan pipeline generation validation failed: swapchain teardown destroys current pipelines")
    if partial.index("g_vkDeviceWaitIdle") > partial.index("xr_vk_destroy_stale_graphics_pipelines();"):
        raise RuntimeError("Vulkan pipeline generation validation failed: stale pipelines destroyed before device idle")

    print("[vulkan-pipeline-generation] render-pass generations + stale-draw rejection + GPU-idle stale cleanup installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Track Vulkan graphics pipeline ownership across render-pass generations.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
