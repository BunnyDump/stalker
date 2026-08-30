from __future__ import annotations

import argparse
from pathlib import Path


def install_dynamic_state(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan dynamic-state layer requires materialized render-pass frame path")

    text = source.read_text(encoding="utf-8")

    fn_marker = "    PFN_vkCmdEndRenderPass g_vkCmdEndRenderPass = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkCmdSetViewport g_vkCmdSetViewport = NULL;
    PFN_vkCmdSetScissor g_vkCmdSetScissor = NULL;
'''
    if "PFN_vkCmdSetViewport g_vkCmdSetViewport" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan dynamic state: function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkCmdEndRenderPass = NULL;\n"
    clear_block = clear_marker + '''        g_vkCmdSetViewport = NULL;
        g_vkCmdSetScissor = NULL;
'''
    if "        g_vkCmdSetViewport = NULL;\n" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan dynamic state: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkCmdEndRenderPass);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCmdSetViewport);
        XR_VK_LOAD_DEVICE(vkCmdSetScissor);
'''
    if "XR_VK_LOAD_DEVICE(vkCmdSetViewport)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan dynamic state: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    draw_marker = '''    g_vkCmdBeginRenderPass(g_command_buffers[image_index], &frame_render_pass, VK_SUBPASS_CONTENTS_INLINE);
    g_vkCmdEndRenderPass(g_command_buffers[image_index]);
'''
    draw_block = r'''    g_vkCmdBeginRenderPass(g_command_buffers[image_index], &frame_render_pass, VK_SUBPASS_CONTENTS_INLINE);

    VkViewport frame_viewport = {};
    frame_viewport.x = 0.0f;
    frame_viewport.y = 0.0f;
    frame_viewport.width = static_cast<float>(g_swapchain_extent.width);
    frame_viewport.height = static_cast<float>(g_swapchain_extent.height);
    frame_viewport.minDepth = 0.0f;
    frame_viewport.maxDepth = 1.0f;
    g_vkCmdSetViewport(g_command_buffers[image_index], 0, 1, &frame_viewport);

    VkRect2D frame_scissor = {};
    frame_scissor.offset.x = 0;
    frame_scissor.offset.y = 0;
    frame_scissor.extent = g_swapchain_extent;
    g_vkCmdSetScissor(g_command_buffers[image_index], 0, 1, &frame_scissor);

    g_vkCmdEndRenderPass(g_command_buffers[image_index]);
'''
    if "VkViewport frame_viewport" not in text:
        if draw_marker not in text:
            raise RuntimeError("Vulkan dynamic state: render-pass command marker not found")
        text = text.replace(draw_marker, draw_block, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "vkCmdSetViewport",
        "vkCmdSetScissor",
        "VkViewport frame_viewport",
        "frame_viewport.width = static_cast<float>(g_swapchain_extent.width)",
        "VkRect2D frame_scissor",
        "frame_scissor.extent = g_swapchain_extent",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan dynamic-state validation failed: missing {token}")

    print("[vulkan-dynamic-state] viewport/scissor commands are recorded inside the native render pass")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install dynamic viewport/scissor command recording for RC6 Vulkan.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_dynamic_state(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
