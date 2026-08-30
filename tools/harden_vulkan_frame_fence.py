from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    old_reset = '''    if (g_vkResetFences(g_device, 1, &g_frame_fence) != VK_SUCCESS ||
        g_vkResetCommandBuffer(g_command_buffers[image_index], 0) != VK_SUCCESS)
        return false;
'''
    new_reset = '''    if (g_vkResetCommandBuffer(g_command_buffers[image_index], 0) != VK_SUCCESS)
        return false;
'''
    if old_reset in text:
        text = text.replace(old_reset, new_reset, 1)
    elif new_reset not in text:
        raise RuntimeError("Vulkan frame-fence hardening: pre-record reset marker not found")

    helper_marker = "    bool xr_vk_create_swapchain(unsigned width, unsigned height)\n"
    helper = '''    bool xr_vk_restore_signaled_frame_fence()
    {
        if (g_device == VK_NULL_HANDLE || !g_vkCreateFence || !g_vkDestroyFence)
            return false;
        if (g_frame_fence != VK_NULL_HANDLE)
            g_vkDestroyFence(g_device, g_frame_fence, NULL);
        g_frame_fence = VK_NULL_HANDLE;

        VkFenceCreateInfo fence_info = {};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        return g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) == VK_SUCCESS;
    }

'''
    if "bool xr_vk_restore_signaled_frame_fence()" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan frame-fence hardening: swapchain helper marker not found")
        text = text.replace(helper_marker, helper + helper_marker, 1)

    old_submit = '''    if (g_vkQueueSubmit(g_graphics_queue, 1, &submit, g_frame_fence) != VK_SUCCESS)
        return false;
'''
    new_submit = '''    if (g_vkResetFences(g_device, 1, &g_frame_fence) != VK_SUCCESS)
        return false;
    if (g_vkQueueSubmit(g_graphics_queue, 1, &submit, g_frame_fence) != VK_SUCCESS)
    {
        xr_vk_restore_signaled_frame_fence();
        return false;
    }
'''
    if old_submit in text:
        text = text.replace(old_submit, new_submit, 1)
    elif new_submit not in text:
        raise RuntimeError("Vulkan frame-fence hardening: queue-submit marker not found")

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "bool xr_vk_restore_signaled_frame_fence()",
        "VK_FENCE_CREATE_SIGNALED_BIT",
        "if (g_vkResetCommandBuffer(g_command_buffers[image_index], 0) != VK_SUCCESS)",
        "if (g_vkResetFences(g_device, 1, &g_frame_fence) != VK_SUCCESS)",
        "xr_vk_restore_signaled_frame_fence();",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan frame-fence hardening validation failed: missing {token}")

    frame_start = final.find("bool xr_vk_bootstrap_frame()")
    runtime_ready = final.find("bool xr_vk_bootstrap_runtime_ready()", frame_start)
    if frame_start < 0 or runtime_ready < 0:
        raise RuntimeError("Vulkan frame-fence hardening: frame function not found")
    frame = final[frame_start:runtime_ready]
    command_reset = frame.find("g_vkResetCommandBuffer")
    fence_reset = frame.find("g_vkResetFences")
    queue_submit = frame.find("g_vkQueueSubmit")
    if min(command_reset, fence_reset, queue_submit) < 0 or not command_reset < fence_reset < queue_submit:
        raise RuntimeError("Vulkan frame-fence hardening: unsafe reset/submit order remains")

    print("[vulkan-frame-fence] fence reset deferred until submit; failed submit restores a signaled fence")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Vulkan frame fence lifecycle against pre-submit and submit failures.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
