from __future__ import annotations

import argparse
from pathlib import Path


def install_command_recording(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan command recording requires the materialized render core")

    text = source.read_text(encoding="utf-8")
    header_text = header.read_text(encoding="utf-8")

    frame_decl = "bool xr_vk_bootstrap_frame();\n"
    recording_decls = frame_decl + (
        "bool xr_vk_bootstrap_frame_begin();\n"
        "bool xr_vk_bootstrap_frame_end();\n"
        "bool xr_vk_bootstrap_frame_recording();\n"
    )
    if "xr_vk_bootstrap_frame_begin" not in header_text:
        if frame_decl not in header_text:
            raise RuntimeError("Vulkan command recording: frame declaration marker not found")
        header_text = header_text.replace(frame_decl, recording_decls, 1)
        header.write_text(header_text, encoding="utf-8")

    state_marker = "    xr_vector<VkCommandBuffer> g_command_buffers;\n"
    state_block = state_marker + (
        "    VkCommandBuffer g_active_command_buffer = VK_NULL_HANDLE;\n"
        "    unsigned g_active_image_index = ~0u;\n"
        "    bool g_frame_recording = false;\n"
    )
    if "g_active_command_buffer" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan command recording: command-buffer state marker not found")
        text = text.replace(state_marker, state_block, 1)

    fn_marker = "    PFN_vkDestroyPipeline g_vkDestroyPipeline = NULL;\n"
    fn_block = fn_marker + (
        "    PFN_vkCmdBeginRenderPass g_vkCmdBeginRenderPass = NULL;\n"
        "    PFN_vkCmdEndRenderPass g_vkCmdEndRenderPass = NULL;\n"
        "    PFN_vkCmdSetViewport g_vkCmdSetViewport = NULL;\n"
        "    PFN_vkCmdSetScissor g_vkCmdSetScissor = NULL;\n"
    )
    if "g_vkCmdBeginRenderPass" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan command recording: pipeline function marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkDestroyPipeline = NULL;\n"
    clear_block = clear_marker + (
        "        g_vkCmdBeginRenderPass = NULL;\n"
        "        g_vkCmdEndRenderPass = NULL;\n"
        "        g_vkCmdSetViewport = NULL;\n"
        "        g_vkCmdSetScissor = NULL;\n"
    )
    if "g_vkCmdBeginRenderPass = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan command recording: function reset marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkDestroyPipeline);\n"
    load_block = load_marker + (
        "        XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass);\n"
        "        XR_VK_LOAD_DEVICE(vkCmdEndRenderPass);\n"
        "        XR_VK_LOAD_DEVICE(vkCmdSetViewport);\n"
        "        XR_VK_LOAD_DEVICE(vkCmdSetScissor);\n"
    )
    if "XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan command recording: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    # Ensure frame-resource destruction cannot leave stale recording state.
    destroy_marker = "    void xr_vk_destroy_frame_resources()\n    {\n"
    destroy_prefix = destroy_marker + (
        "        g_frame_recording = false;\n"
        "        g_active_command_buffer = VK_NULL_HANDLE;\n"
        "        g_active_image_index = ~0u;\n"
    )
    if "g_active_image_index = ~0u;" not in text[text.find(destroy_marker):text.find(destroy_marker) + 400]:
        if destroy_marker not in text:
            raise RuntimeError("Vulkan command recording: frame-resource destroy marker not found")
        text = text.replace(destroy_marker, destroy_prefix, 1)

    frame_start = text.find("bool xr_vk_bootstrap_frame()\n{")
    ready_start = text.find("bool xr_vk_bootstrap_runtime_ready()\n", frame_start)
    if frame_start < 0 or ready_start < 0:
        raise RuntimeError("Vulkan command recording: bootstrap frame implementation markers not found")

    replacement = r'''bool xr_vk_bootstrap_frame_begin()
{
    if (g_frame_recording || !xr_vk_bootstrap_runtime_ready() ||
        g_render_pass == VK_NULL_HANDLE || g_framebuffers.empty() ||
        !g_vkCmdBeginRenderPass || !g_vkCmdEndRenderPass || !g_vkCmdSetViewport || !g_vkCmdSetScissor)
        return false;

    if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
        return false;

    unsigned image_index = 0;
    const VkResult acquire = g_vkAcquireNextImageKHR(
        g_device, g_swapchain, ~0ull, g_image_available, VK_NULL_HANDLE, &image_index);
    if (acquire == VK_ERROR_OUT_OF_DATE_KHR)
        return false;
    if (acquire != VK_SUCCESS && acquire != VK_SUBOPTIMAL_KHR)
        return false;
    if (image_index >= g_command_buffers.size() || image_index >= g_framebuffers.size())
        return false;

    VkCommandBuffer command_buffer = g_command_buffers[image_index];
    if (g_vkResetCommandBuffer(command_buffer, 0) != VK_SUCCESS)
        return false;

    VkCommandBufferBeginInfo begin_info = {};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    begin_info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    if (g_vkBeginCommandBuffer(command_buffer, &begin_info) != VK_SUCCESS)
        return false;

    VkClearValue clear_values[2] = {};
    clear_values[0].color.float32[0] = 0.015f;
    clear_values[0].color.float32[1] = 0.025f;
    clear_values[0].color.float32[2] = 0.040f;
    clear_values[0].color.float32[3] = 1.0f;
    clear_values[1].depthStencil.depth = 1.0f;
    clear_values[1].depthStencil.stencil = 0;

    VkRenderPassBeginInfo render_pass = {};
    render_pass.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    render_pass.renderPass = g_render_pass;
    render_pass.framebuffer = g_framebuffers[image_index];
    render_pass.renderArea.offset.x = 0;
    render_pass.renderArea.offset.y = 0;
    render_pass.renderArea.extent = g_swapchain_extent;
    render_pass.clearValueCount = 2;
    render_pass.pClearValues = clear_values;
    g_vkCmdBeginRenderPass(command_buffer, &render_pass, VK_SUBPASS_CONTENTS_INLINE);

    VkViewport viewport = {};
    viewport.x = 0.0f;
    viewport.y = 0.0f;
    viewport.width = static_cast<float>(g_swapchain_extent.width);
    viewport.height = static_cast<float>(g_swapchain_extent.height);
    viewport.minDepth = 0.0f;
    viewport.maxDepth = 1.0f;
    g_vkCmdSetViewport(command_buffer, 0, 1, &viewport);

    VkRect2D scissor = {};
    scissor.offset.x = 0;
    scissor.offset.y = 0;
    scissor.extent = g_swapchain_extent;
    g_vkCmdSetScissor(command_buffer, 0, 1, &scissor);

    g_active_command_buffer = command_buffer;
    g_active_image_index = image_index;
    g_frame_recording = true;
    return true;
}

bool xr_vk_bootstrap_frame_end()
{
    if (!g_frame_recording || g_active_command_buffer == VK_NULL_HANDLE ||
        g_active_image_index >= g_swapchain_images.size())
        return false;

    const VkCommandBuffer command_buffer = g_active_command_buffer;
    const unsigned image_index = g_active_image_index;
    g_vkCmdEndRenderPass(command_buffer);
    if (g_vkEndCommandBuffer(command_buffer) != VK_SUCCESS)
    {
        g_frame_recording = false;
        g_active_command_buffer = VK_NULL_HANDLE;
        g_active_image_index = ~0u;
        return false;
    }

    if (g_vkResetFences(g_device, 1, &g_frame_fence) != VK_SUCCESS)
        return false;

    const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    VkSubmitInfo submit = {};
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit.waitSemaphoreCount = 1;
    submit.pWaitSemaphores = &g_image_available;
    submit.pWaitDstStageMask = &wait_stage;
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &command_buffer;
    submit.signalSemaphoreCount = 1;
    submit.pSignalSemaphores = &g_render_finished;
    if (g_vkQueueSubmit(g_graphics_queue, 1, &submit, g_frame_fence) != VK_SUCCESS)
    {
        g_frame_recording = false;
        g_active_command_buffer = VK_NULL_HANDLE;
        g_active_image_index = ~0u;
        return false;
    }

    VkPresentInfoKHR present = {};
    present.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    present.waitSemaphoreCount = 1;
    present.pWaitSemaphores = &g_render_finished;
    present.swapchainCount = 1;
    present.pSwapchains = &g_swapchain;
    present.pImageIndices = &image_index;
    const VkResult presented = g_vkQueuePresentKHR(g_present_queue, &present);
    g_image_initialized[image_index] = 1;

    g_frame_recording = false;
    g_active_command_buffer = VK_NULL_HANDLE;
    g_active_image_index = ~0u;
    return presented == VK_SUCCESS || presented == VK_SUBOPTIMAL_KHR;
}

bool xr_vk_bootstrap_frame_recording()
{
    return g_frame_recording && g_active_command_buffer != VK_NULL_HANDLE;
}

bool xr_vk_bootstrap_frame()
{
    if (!xr_vk_bootstrap_frame_begin())
        return false;
    return xr_vk_bootstrap_frame_end();
}

'''
    text = text[:frame_start] + replacement + text[ready_start:]
    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    for token in (
        "xr_vk_bootstrap_frame_begin", "xr_vk_bootstrap_frame_end", "g_active_command_buffer",
        "vkCmdBeginRenderPass", "VK_SUBPASS_CONTENTS_INLINE", "VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan command recording validation failed: missing {token}")
    if "g_vkCmdClearColorImage(g_command_buffers[image_index]" in final:
        raise RuntimeError("legacy bootstrap transfer-clear frame body remains after command-recording split")
    print("[vulkan-command-recording] frame split into acquire/begin-render-pass and submit/present phases")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install recordable Vulkan frame begin/end phases for RC6 xrRender_VK.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    install_command_recording(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
