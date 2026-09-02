from __future__ import annotations

import argparse
from pathlib import Path


def install_renderpass_frame(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan render-pass frame path requires materialized render core")

    text = source.read_text(encoding="utf-8")

    fn_marker = "    PFN_vkCmdClearColorImage g_vkCmdClearColorImage = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkCmdBeginRenderPass g_vkCmdBeginRenderPass = NULL;
    PFN_vkCmdEndRenderPass g_vkCmdEndRenderPass = NULL;
'''
    if "PFN_vkCmdBeginRenderPass g_vkCmdBeginRenderPass" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan render-pass frame: function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkCmdClearColorImage = NULL;\n"
    clear_block = clear_marker + '''        g_vkCmdBeginRenderPass = NULL;
        g_vkCmdEndRenderPass = NULL;
'''
    if "        g_vkCmdBeginRenderPass = NULL;\n" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan render-pass frame: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkCmdClearColorImage);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass);
        XR_VK_LOAD_DEVICE(vkCmdEndRenderPass);
'''
    if "XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan render-pass frame: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    if "VkRenderPassBeginInfo frame_render_pass" not in text:
        start_marker = "    VkImageMemoryBarrier to_transfer = {};\n"
        end_marker = "    if (g_vkEndCommandBuffer(g_command_buffers[image_index]) != VK_SUCCESS)\n"
        start = text.find(start_marker)
        end = text.find(end_marker, start)
        if start < 0 or end < 0:
            raise RuntimeError("Vulkan render-pass frame: legacy transfer-clear block not found")

        replacement = r'''    if (g_render_pass == VK_NULL_HANDLE || image_index >= g_framebuffers.size() ||
        g_framebuffers[image_index] == VK_NULL_HANDLE)
        return false;

    VkClearValue clear_values[2] = {};
    clear_values[0].color.float32[0] = 0.015f;
    clear_values[0].color.float32[1] = 0.020f;
    clear_values[0].color.float32[2] = 0.028f;
    clear_values[0].color.float32[3] = 1.0f;
    clear_values[1].depthStencil.depth = 1.0f;
    clear_values[1].depthStencil.stencil = 0;

    VkRenderPassBeginInfo frame_render_pass = {};
    frame_render_pass.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    frame_render_pass.renderPass = g_render_pass;
    frame_render_pass.framebuffer = g_framebuffers[image_index];
    frame_render_pass.renderArea.offset.x = 0;
    frame_render_pass.renderArea.offset.y = 0;
    frame_render_pass.renderArea.extent = g_swapchain_extent;
    frame_render_pass.clearValueCount = 2;
    frame_render_pass.pClearValues = clear_values;

    g_vkCmdBeginRenderPass(g_command_buffers[image_index], &frame_render_pass, VK_SUBPASS_CONTENTS_INLINE);
    g_vkCmdEndRenderPass(g_command_buffers[image_index]);

'''
        text = text[:start] + replacement + text[end:]

    transfer_wait = "    const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;\n"
    color_wait = "    const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;\n"
    if transfer_wait in text:
        text = text.replace(transfer_wait, color_wait, 1)
    elif color_wait not in text:
        raise RuntimeError("Vulkan render-pass frame: submit wait-stage marker not found")

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "vkCmdBeginRenderPass",
        "vkCmdEndRenderPass",
        "VkRenderPassBeginInfo frame_render_pass",
        "frame_render_pass.framebuffer = g_framebuffers[image_index]",
        "clear_values[1].depthStencil.depth = 1.0f",
        "VK_SUBPASS_CONTENTS_INLINE",
        "const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan render-pass frame validation failed: missing {token}")

    legacy = (
        "VkImageMemoryBarrier to_transfer = {};",
        "g_vkCmdClearColorImage(g_command_buffers[image_index]",
        "VkImageMemoryBarrier to_present = to_transfer;",
        "const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;",
    )
    for token in legacy:
        if token in final:
            raise RuntimeError(f"Vulkan render-pass frame validation failed: legacy frame path remains: {token}")

    print("[vulkan-frame] swapchain frame now records native render-pass + color/depth clears with color-output synchronization")


def main() -> int:
    parser = argparse.ArgumentParser(description="Route RC6 Vulkan presentation through the native render-pass/framebuffer path.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_renderpass_frame(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
