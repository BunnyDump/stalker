from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    render = renderer / "r2_R_render.cpp"
    lifecycle = renderer / "r2.cpp"
    for path in (source, header, render, lifecycle):
        if not path.is_file():
            raise FileNotFoundError(path)

    text = source.read_text(encoding="utf-8")
    h = header.read_text(encoding="utf-8")
    r = render.read_text(encoding="utf-8")
    life = lifecycle.read_text(encoding="utf-8")

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
        "bool g_frame_recording = false;",
        "unsigned g_active_frame_image_index = ~0u;",
        "bool xr_vk_bootstrap_begin_frame()",
        "bool xr_vk_bootstrap_end_frame()",
        "void* xr_vk_bootstrap_active_command_buffer()",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError("Vulkan frame-path validation failed; missing: " + ", ".join(missing))

    for token in (
        "bool xr_vk_bootstrap_begin_frame();",
        "bool xr_vk_bootstrap_end_frame();",
        "void* xr_vk_bootstrap_active_command_buffer();",
    ):
        if token not in h:
            raise RuntimeError(f"Vulkan frame-path validation failed: public lifecycle declaration missing {token}")

    forbidden = (
        "VkImageMemoryBarrier to_transfer = {};",
        "g_vkCmdClearColorImage(g_command_buffers[image_index]",
        "VkImageMemoryBarrier to_present = to_transfer;",
        "const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;",
    )
    stale = [token for token in forbidden if token in text]
    if stale:
        raise RuntimeError("Vulkan frame-path validation failed; legacy transfer-clear path remains: " + ", ".join(stale))

    begin_start = text.find("bool xr_vk_bootstrap_begin_frame()")
    end_start = text.find("bool xr_vk_bootstrap_end_frame()", begin_start)
    wrapper_start = text.find("bool xr_vk_bootstrap_frame()", end_start)
    runtime_ready = text.find("bool xr_vk_bootstrap_runtime_ready()", wrapper_start)
    if min(begin_start, end_start, wrapper_start, runtime_ready) < 0:
        raise RuntimeError("Vulkan frame-path validation failed: split lifecycle boundaries not found")
    if not begin_start < end_start < wrapper_start < runtime_ready:
        raise RuntimeError("Vulkan frame-path validation failed: split lifecycle function order invalid")

    begin = text[begin_start:end_start]
    end = text[end_start:wrapper_start]
    wrapper = text[wrapper_start:runtime_ready]

    begin_order = (
        "g_vkBeginCommandBuffer",
        "g_vkCmdBeginRenderPass",
        "g_vkCmdSetViewport",
        "g_vkCmdSetScissor",
        "g_active_frame_image_index = image_index",
        "g_frame_recording = true",
    )
    begin_positions = [begin.find(token) for token in begin_order]
    if any(pos < 0 for pos in begin_positions) or begin_positions != sorted(begin_positions):
        raise RuntimeError("Vulkan frame-path validation failed: begin-frame recording order invalid")

    end_order = (
        "g_vkCmdEndRenderPass",
        "g_vkEndCommandBuffer",
        "g_vkResetFences",
        "g_vkQueueSubmit",
        "g_vkQueuePresentKHR",
        "xr_vk_clear_active_frame_state()",
    )
    end_positions = [end.find(token) for token in end_order]
    if any(pos < 0 for pos in end_positions) or end_positions != sorted(end_positions):
        raise RuntimeError("Vulkan frame-path validation failed: end-frame submit/present order invalid")

    if "g_render_pass == VK_NULL_HANDLE" not in begin or "image_index >= g_framebuffers.size()" not in begin:
        raise RuntimeError("Vulkan frame-path validation failed: begin-frame render-pass/framebuffer guards missing")
    if "xr_vk_bootstrap_begin_frame()" not in wrapper or "xr_vk_bootstrap_end_frame()" not in wrapper:
        raise RuntimeError("Vulkan frame-path validation failed: compatibility frame wrapper incomplete")

    render_required = (
        '#include "vk_bootstrap.h"',
        "class xr_vk_render_frame_scope",
        "xr_vk_bootstrap_runtime_ready()",
        'strstr(Core.Params, "-vkpresent")',
        "active_ = xr_vk_bootstrap_begin_frame();",
        "xr_vk_bootstrap_end_frame()",
        "xr_vk_render_frame_scope vk_frame_scope;",
        "void CRender::Render()",
    )
    for token in render_required:
        if token not in r:
            raise RuntimeError(f"Vulkan frame-path validation failed: R2 render scope missing {token}")

    render_fn = r.find("void CRender::Render()")
    scope_pos = r.find("xr_vk_render_frame_scope vk_frame_scope;", render_fn)
    first_menu_return = r.find("return;", render_fn)
    if min(render_fn, scope_pos, first_menu_return) < 0 or not render_fn < scope_pos < first_menu_return:
        raise RuntimeError("Vulkan frame-path validation failed: RAII scope does not cover early Render returns")

    if "xr_vk_bootstrap_frame();" in life:
        raise RuntimeError("Vulkan frame-path validation failed: stale OnFrame presentation hook remains")

    print("[vulkan-frame-validate] R2 Render-scoped begin/end render pass, active command buffer, dynamic state, safe submit/present and RAII early-return coverage verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate split RC6 Vulkan recording across the real R2 Render phase.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())