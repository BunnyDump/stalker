from __future__ import annotations

import argparse
from pathlib import Path


UPLOAD_CAPACITY_LITERAL = "67108864ull"


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    # Swapchain recreation must not invalidate long-lived material descriptors, sampler,
    # pipeline layout/cache, uniform/upload buffers, or dynamic stream buffers.
    fn = text.find("    void xr_vk_destroy_frame_resources()\n    {")
    window = text.find("    void xr_vk_destroy_window_runtime()", fn)
    if fn < 0 or window < 0:
        raise RuntimeError("Vulkan resource lifetime: destroy functions not found")

    if "void xr_vk_destroy_swapchain_resources()" not in text:
        partial = r'''    void xr_vk_destroy_swapchain_resources()
    {
        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);

        for (u32 i = 0; i < g_framebuffers.size(); ++i)
            if (g_framebuffers[i] != VK_NULL_HANDLE && g_vkDestroyFramebuffer)
                g_vkDestroyFramebuffer(g_device, g_framebuffers[i], NULL);
        g_framebuffers.clear();
        if (g_render_pass != VK_NULL_HANDLE && g_vkDestroyRenderPass)
            g_vkDestroyRenderPass(g_device, g_render_pass, NULL);
        if (g_depth_view != VK_NULL_HANDLE && g_vkDestroyImageView)
            g_vkDestroyImageView(g_device, g_depth_view, NULL);
        if (g_depth_image != VK_NULL_HANDLE && g_vkDestroyImage)
            g_vkDestroyImage(g_device, g_depth_image, NULL);
        if (g_depth_memory != VK_NULL_HANDLE && g_vkFreeMemory)
            g_vkFreeMemory(g_device, g_depth_memory, NULL);
        g_render_pass = VK_NULL_HANDLE;
        g_depth_view = VK_NULL_HANDLE;
        g_depth_image = VK_NULL_HANDLE;
        g_depth_memory = VK_NULL_HANDLE;
        g_depth_format = VK_FORMAT_UNDEFINED;

        if (g_device != VK_NULL_HANDLE && g_vkDestroyFence && g_frame_fence != VK_NULL_HANDLE)
            g_vkDestroyFence(g_device, g_frame_fence, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroySemaphore && g_render_finished != VK_NULL_HANDLE)
            g_vkDestroySemaphore(g_device, g_render_finished, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroySemaphore && g_image_available != VK_NULL_HANDLE)
            g_vkDestroySemaphore(g_device, g_image_available, NULL);
        g_frame_fence = VK_NULL_HANDLE;
        g_render_finished = VK_NULL_HANDLE;
        g_image_available = VK_NULL_HANDLE;
        g_frame_submission_pending = false;

        if (g_device != VK_NULL_HANDLE && g_vkDestroyCommandPool && g_command_pool != VK_NULL_HANDLE)
            g_vkDestroyCommandPool(g_device, g_command_pool, NULL);
        g_command_pool = VK_NULL_HANDLE;
        g_command_buffers.clear();

        if (g_device != VK_NULL_HANDLE && g_vkDestroyImageView)
            for (u32 i = 0; i < g_swapchain_views.size(); ++i)
                if (g_swapchain_views[i] != VK_NULL_HANDLE)
                    g_vkDestroyImageView(g_device, g_swapchain_views[i], NULL);
        g_swapchain_views.clear();
        g_swapchain_images.clear();
        g_image_initialized.clear();
        if (g_device != VK_NULL_HANDLE && g_vkDestroySwapchainKHR && g_swapchain != VK_NULL_HANDLE)
            g_vkDestroySwapchainKHR(g_device, g_swapchain, NULL);
        g_swapchain = VK_NULL_HANDLE;
        g_swapchain_format = VK_FORMAT_UNDEFINED;
        g_swapchain_extent.width = 0;
        g_swapchain_extent.height = 0;
    }

'''
        text = text[:fn] + partial + text[fn:]

    # Resize/out-of-date paths use the partial destroyer; shutdown keeps the full destroyer.
    resize_start = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)")
    recreate_start = text.find("bool xr_vk_recreate_swapchain_from_window()")
    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    if resize_start < 0 or recreate_start < 0 or frame_start < 0:
        raise RuntimeError("Vulkan resource lifetime: swapchain recreation helpers not found")
    segment = text[resize_start:frame_start]
    segment = segment.replace("xr_vk_destroy_frame_resources();", "xr_vk_destroy_swapchain_resources();")
    text = text[:resize_start] + segment + text[frame_start:]

    replacements = {
        "        if (g_vkCreateDescriptorSetLayout(g_device, &descriptor_layout, NULL, &g_descriptor_set_layout) != VK_SUCCESS)\n            return false;\n":
        "        if (g_descriptor_set_layout == VK_NULL_HANDLE &&\n            g_vkCreateDescriptorSetLayout(g_device, &descriptor_layout, NULL, &g_descriptor_set_layout) != VK_SUCCESS)\n            return false;\n",
        "        if (g_vkCreatePipelineLayout(g_device, &pipeline_layout, NULL, &g_pipeline_layout) != VK_SUCCESS)\n            return false;\n":
        "        if (g_pipeline_layout == VK_NULL_HANDLE &&\n            g_vkCreatePipelineLayout(g_device, &pipeline_layout, NULL, &g_pipeline_layout) != VK_SUCCESS)\n            return false;\n",
        "        if (g_vkCreateDescriptorPool(g_device, &pool, NULL, &g_descriptor_pool) != VK_SUCCESS)\n            return false;\n":
        "        if (g_descriptor_pool == VK_NULL_HANDLE &&\n            g_vkCreateDescriptorPool(g_device, &pool, NULL, &g_descriptor_pool) != VK_SUCCESS)\n            return false;\n",
        "        if (g_vkCreateSampler(g_device, &sampler, NULL, &g_default_sampler) != VK_SUCCESS)\n            return false;\n":
        "        if (g_default_sampler == VK_NULL_HANDLE &&\n            g_vkCreateSampler(g_device, &sampler, NULL, &g_default_sampler) != VK_SUCCESS)\n            return false;\n",
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise RuntimeError("Vulkan resource lifetime: persistent creation marker changed")

    cache_old = "        if (g_vkCreatePipelineCache(g_device, &pipeline_cache_info, NULL, &g_pipeline_cache) != VK_SUCCESS)\n            return false;\n"
    cache_new = "        if (g_pipeline_cache == VK_NULL_HANDLE &&\n            g_vkCreatePipelineCache(g_device, &pipeline_cache_info, NULL, &g_pipeline_cache) != VK_SUCCESS)\n            return false;\n"
    if cache_old in text:
        text = text.replace(cache_old, cache_new, 1)
    elif cache_new not in text:
        raise RuntimeError("Vulkan resource lifetime: pipeline cache creation marker changed")

    for size_expr, usage, buffer_name, memory_name in (
        ("64 * 1024", "VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT", "g_uniform_buffer", "g_uniform_memory"),
        (UPLOAD_CAPACITY_LITERAL, "VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_INDEX_BUFFER_BIT", "g_upload_buffer", "g_upload_memory"),
    ):
        old = f'''        if (!xr_vk_create_buffer({size_expr}, {usage},\n                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, {buffer_name}, {memory_name}))\n            return false;\n'''
        new = f'''        if ({buffer_name} == VK_NULL_HANDLE &&\n            !xr_vk_create_buffer({size_expr}, {usage},\n                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, {buffer_name}, {memory_name}))\n            return false;\n'''
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise RuntimeError(f"Vulkan resource lifetime: {buffer_name} creation marker changed")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "void xr_vk_destroy_swapchain_resources()",
        "g_descriptor_set_layout == VK_NULL_HANDLE",
        "g_pipeline_layout == VK_NULL_HANDLE",
        "g_descriptor_pool == VK_NULL_HANDLE",
        "g_default_sampler == VK_NULL_HANDLE",
        "g_pipeline_cache == VK_NULL_HANDLE",
        "g_uniform_buffer == VK_NULL_HANDLE",
        "g_upload_buffer == VK_NULL_HANDLE",
        f"xr_vk_create_buffer({UPLOAD_CAPACITY_LITERAL}",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan resource lifetime validation failed: missing {token}")

    resize = final[final.index("bool xr_vk_bootstrap_resize"):final.index("bool xr_vk_bootstrap_frame")]
    if "xr_vk_destroy_frame_resources();" in resize:
        raise RuntimeError("Vulkan resource lifetime validation failed: resize still destroys device-lifetime resources")
    if resize.count("xr_vk_destroy_swapchain_resources();") < 2:
        raise RuntimeError("Vulkan resource lifetime validation failed: resize/recreate do not use partial teardown")

    partial_start = final.index("void xr_vk_destroy_swapchain_resources()")
    full_start = final.index("void xr_vk_destroy_frame_resources()", partial_start)
    partial = final[partial_start:full_start]
    forbidden = (
        "g_vkDestroyDescriptorPool", "g_vkDestroyDescriptorSetLayout", "g_vkDestroyPipelineLayout",
        "g_vkDestroyPipelineCache", "g_vkDestroySampler", "g_uniform_buffer", "g_upload_buffer",
        "g_stream_vertex_buffer", "g_stream_index_buffer",
    )
    for token in forbidden:
        if token in partial:
            raise RuntimeError(f"Vulkan resource lifetime validation failed: swapchain teardown owns {token}")

    print("[vulkan-lifetime] swapchain teardown separated from persistent descriptor/sampler/pipeline/buffer lifetime")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preserve Vulkan material/device resources across swapchain recreation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
