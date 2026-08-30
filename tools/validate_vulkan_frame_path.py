from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(f"Materialized Vulkan bootstrap not found: {source}")

    text = source.read_text(encoding="utf-8")

    required = (
        "PFN_vkCmdBeginRenderPass g_vkCmdBeginRenderPass",
        "PFN_vkCmdEndRenderPass g_vkCmdEndRenderPass",
        "PFN_vkCmdSetViewport g_vkCmdSetViewport",
        "PFN_vkCmdSetScissor g_vkCmdSetScissor",
        "XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass)",
        "XR_VK_LOAD_DEVICE(vkCmdEndRenderPass)",
        "XR_VK_LOAD_DEVICE(vkCmdSetViewport)",
        "XR_VK_LOAD_DEVICE(vkCmdSetScissor)",
        "VkRenderPassBeginInfo frame_render_pass",
        "frame_render_pass.framebuffer = g_framebuffers[image_index]",
        "clear_values[1].depthStencil.depth = 1.0f",
        "g_vkCmdBeginRenderPass(g_command_buffers[image_index]",
        "VkViewport frame_viewport",
        "g_vkCmdSetViewport(g_command_buffers[image_index]",
        "VkRect2D frame_scissor",
        "g_vkCmdSetScissor(g_command_buffers[image_index]",
        "g_vkCmdEndRenderPass(g_command_buffers[image_index])",
        "const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;",
        "VkGraphicsPipelineCreateInfo info = {}",
        "g_vkCreateGraphicsPipelines(g_device, g_pipeline_cache",
        "VK_DYNAMIC_STATE_VIEWPORT",
        "VK_DYNAMIC_STATE_SCISSOR",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError("Vulkan frame-path validation failed; missing: " + ", ".join(missing))

    forbidden = (
        "VkImageMemoryBarrier to_transfer = {};",
        "g_vkCmdClearColorImage(g_command_buffers[image_index]",
        "VkImageMemoryBarrier to_present = to_transfer;",
        "const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;",
    )
    stale = [token for token in forbidden if token in text]
    if stale:
        raise RuntimeError("Vulkan frame-path validation failed; legacy transfer-clear path remains: " + ", ".join(stale))

    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    if frame_start < 0:
        raise RuntimeError("Vulkan frame-path validation failed: xr_vk_bootstrap_frame not found")
    frame_end = text.find("bool xr_vk_bootstrap_runtime_ready()", frame_start)
    if frame_end < 0:
        raise RuntimeError("Vulkan frame-path validation failed: frame function boundary not found")
    frame = text[frame_start:frame_end]

    ordered = (
        "g_vkBeginCommandBuffer",
        "g_vkCmdBeginRenderPass",
        "g_vkCmdSetViewport",
        "g_vkCmdSetScissor",
        "g_vkCmdEndRenderPass",
        "g_vkEndCommandBuffer",
        "g_vkQueueSubmit",
        "g_vkQueuePresentKHR",
    )
    positions = [frame.find(token) for token in ordered]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise RuntimeError("Vulkan frame-path validation failed: command recording/submission order is invalid")

    if "g_render_pass == VK_NULL_HANDLE" not in frame or "image_index >= g_framebuffers.size()" not in frame:
        raise RuntimeError("Vulkan frame-path validation failed: render-pass/framebuffer guards are missing")

    print("[vulkan-frame-validate] native render-pass frame path, dynamic state, pipeline compatibility and synchronization verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the materialized RC6 Vulkan render-pass frame path.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
