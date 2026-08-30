from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    signature_old = "    bool xr_vk_create_swapchain(unsigned width, unsigned height)\n    {\n"
    signature_new = "    bool xr_vk_create_swapchain(unsigned width, unsigned height, VkSwapchainKHR old_swapchain = VK_NULL_HANDLE)\n    {\n"
    if signature_new not in text:
        if signature_old not in text:
            raise RuntimeError("Transactional swapchain: create function marker not found")
        text = text.replace(signature_old, signature_new, 1)

    old_field = "        info.oldSwapchain = VK_NULL_HANDLE;\n"
    new_field = "        info.oldSwapchain = old_swapchain;\n"
    if new_field not in text:
        if old_field not in text:
            raise RuntimeError("Transactional swapchain: oldSwapchain marker not found")
        text = text.replace(old_field, new_field, 1)

    helper_marker = "    bool xr_vk_create_swapchain(unsigned width, unsigned height, VkSwapchainKHR old_swapchain = VK_NULL_HANDLE)\n"
    helper = r'''    struct xr_vk_swapchain_state
    {
        VkSwapchainKHR swapchain;
        VkFormat format;
        VkExtent2D extent;
        VkCommandPool command_pool;
        VkSemaphore image_available;
        VkSemaphore render_finished;
        VkFence frame_fence;
        bool frame_submission_pending;
        VkImage depth_image;
        VkDeviceMemory depth_memory;
        VkImageView depth_view;
        VkFormat depth_format;
        VkRenderPass render_pass;
        unsigned requested_width;
        unsigned requested_height;
        xr_vector<VkImage> images;
        xr_vector<VkImageView> views;
        xr_vector<VkCommandBuffer> command_buffers;
        xr_vector<u8> image_initialized;
        xr_vector<VkFramebuffer> framebuffers;
    };

    xr_vk_swapchain_state xr_vk_capture_swapchain_state()
    {
        xr_vk_swapchain_state state;
        state.swapchain = g_swapchain;
        state.format = g_swapchain_format;
        state.extent = g_swapchain_extent;
        state.command_pool = g_command_pool;
        state.image_available = g_image_available;
        state.render_finished = g_render_finished;
        state.frame_fence = g_frame_fence;
        state.frame_submission_pending = g_frame_submission_pending;
        state.depth_image = g_depth_image;
        state.depth_memory = g_depth_memory;
        state.depth_view = g_depth_view;
        state.depth_format = g_depth_format;
        state.render_pass = g_render_pass;
        state.requested_width = g_requested_width;
        state.requested_height = g_requested_height;
        state.images = g_swapchain_images;
        state.views = g_swapchain_views;
        state.command_buffers = g_command_buffers;
        state.image_initialized = g_image_initialized;
        state.framebuffers = g_framebuffers;
        return state;
    }

    void xr_vk_clear_swapchain_state_without_destroy()
    {
        g_swapchain = VK_NULL_HANDLE;
        g_swapchain_format = VK_FORMAT_UNDEFINED;
        g_swapchain_extent.width = 0;
        g_swapchain_extent.height = 0;
        g_command_pool = VK_NULL_HANDLE;
        g_image_available = VK_NULL_HANDLE;
        g_render_finished = VK_NULL_HANDLE;
        g_frame_fence = VK_NULL_HANDLE;
        g_frame_submission_pending = false;
        g_depth_image = VK_NULL_HANDLE;
        g_depth_memory = VK_NULL_HANDLE;
        g_depth_view = VK_NULL_HANDLE;
        g_depth_format = VK_FORMAT_UNDEFINED;
        g_render_pass = VK_NULL_HANDLE;
        g_requested_width = 0;
        g_requested_height = 0;
        g_swapchain_images.clear();
        g_swapchain_views.clear();
        g_command_buffers.clear();
        g_image_initialized.clear();
        g_framebuffers.clear();
    }

    void xr_vk_restore_swapchain_state(const xr_vk_swapchain_state& state)
    {
        g_swapchain = state.swapchain;
        g_swapchain_format = state.format;
        g_swapchain_extent = state.extent;
        g_command_pool = state.command_pool;
        g_image_available = state.image_available;
        g_render_finished = state.render_finished;
        g_frame_fence = state.frame_fence;
        g_frame_submission_pending = state.frame_submission_pending;
        g_depth_image = state.depth_image;
        g_depth_memory = state.depth_memory;
        g_depth_view = state.depth_view;
        g_depth_format = state.depth_format;
        g_render_pass = state.render_pass;
        g_requested_width = state.requested_width;
        g_requested_height = state.requested_height;
        g_swapchain_images = state.images;
        g_swapchain_views = state.views;
        g_command_buffers = state.command_buffers;
        g_image_initialized = state.image_initialized;
        g_framebuffers = state.framebuffers;
    }

'''
    if "struct xr_vk_swapchain_state" not in text:
        if helper_marker not in text:
            raise RuntimeError("Transactional swapchain: helper insertion marker not found")
        text = text.replace(helper_marker, helper + helper_marker, 1)

    transaction_marker = "bool xr_vk_bootstrap_resize(unsigned width, unsigned height)\n"
    transaction = r'''bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)
{
    if (!width || !height || g_device == VK_NULL_HANDLE || g_surface == VK_NULL_HANDLE)
        return false;
    if (g_swapchain == VK_NULL_HANDLE)
        return xr_vk_create_swapchain(width, height);

    if (g_vkDeviceWaitIdle && g_vkDeviceWaitIdle(g_device) != VK_SUCCESS)
        return false;
    xr_vk_collect_deferred_textures();

    const xr_vk_swapchain_state old_state = xr_vk_capture_swapchain_state();
    xr_vk_clear_swapchain_state_without_destroy();

    // Vulkan retires oldSwapchain as soon as vkCreateSwapchainKHR is called with it,
    // even if creation fails. Therefore old_state is retained only for deterministic
    // destruction; it must never be restored as the active rendering swapchain.
    if (!xr_vk_create_swapchain(width, height, old_state.swapchain))
    {
        xr_vk_destroy_swapchain_resources();
        xr_vk_clear_swapchain_state_without_destroy();

        xr_vk_restore_swapchain_state(old_state);
        xr_vk_destroy_swapchain_resources();
        xr_vk_clear_swapchain_state_without_destroy();

        // The retired old swapchain is gone. Make one clean recovery attempt without
        // oldSwapchain; if this also fails, leave globals in an explicit no-swapchain state.
        if (!xr_vk_create_swapchain(width, height, VK_NULL_HANDLE))
        {
            xr_vk_destroy_swapchain_resources();
            xr_vk_clear_swapchain_state_without_destroy();
            return false;
        }
        return true;
    }

    const xr_vk_swapchain_state new_state = xr_vk_capture_swapchain_state();

    // Replacement is complete. Destroy the retired old frame/swapchain state, then
    // restore the fully-created new state as the sole active state.
    xr_vk_clear_swapchain_state_without_destroy();
    xr_vk_restore_swapchain_state(old_state);
    xr_vk_destroy_swapchain_resources();
    xr_vk_clear_swapchain_state_without_destroy();
    xr_vk_restore_swapchain_state(new_state);
    return true;
}

'''
    if "bool xr_vk_transactional_recreate_swapchain" not in text:
        if transaction_marker not in text:
            raise RuntimeError("Transactional swapchain: resize insertion marker not found")
        text = text.replace(transaction_marker, transaction + transaction_marker, 1)

    resize_old = '''    xr_vk_destroy_swapchain_resources();
    return xr_vk_create_swapchain(width, height);
'''
    resize_new = '''    return xr_vk_transactional_recreate_swapchain(width, height);
'''
    resize_start = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)")
    recreate_start = text.find("bool xr_vk_recreate_swapchain_from_window()", resize_start)
    frame_start = text.find("bool xr_vk_bootstrap_frame()", recreate_start)
    if min(resize_start, recreate_start, frame_start) < 0:
        raise RuntimeError("Transactional swapchain: recreation functions not found")
    segment = text[resize_start:frame_start]
    if resize_old in segment:
        segment = segment.replace(resize_old, resize_new)
    if "xr_vk_destroy_swapchain_resources();\n    return xr_vk_create_swapchain(width, height);" in segment:
        raise RuntimeError("Transactional swapchain: destructive recreate path remains")
    if segment.count("xr_vk_transactional_recreate_swapchain(width, height)") < 2:
        raise RuntimeError("Transactional swapchain: resize/window recreation not both converted")
    text = text[:resize_start] + segment + text[frame_start:]

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "info.oldSwapchain = old_swapchain;",
        "struct xr_vk_swapchain_state",
        "xr_vk_capture_swapchain_state()",
        "xr_vk_clear_swapchain_state_without_destroy()",
        "xr_vk_create_swapchain(width, height, old_state.swapchain)",
        "xr_vk_create_swapchain(width, height, VK_NULL_HANDLE)",
        "xr_vk_restore_swapchain_state(new_state);",
        "bool xr_vk_transactional_recreate_swapchain",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Transactional swapchain validation failed: missing {token}")

    tx_start = final.index("bool xr_vk_transactional_recreate_swapchain")
    tx_end = final.index("bool xr_vk_bootstrap_resize", tx_start)
    tx = final[tx_start:tx_end]
    create = tx.index("xr_vk_create_swapchain(width, height, old_state.swapchain)")
    failure_destroy_partial = tx.index("xr_vk_destroy_swapchain_resources();", create)
    failure_restore_old = tx.index("xr_vk_restore_swapchain_state(old_state);", failure_destroy_partial)
    failure_destroy_old = tx.index("xr_vk_destroy_swapchain_resources();", failure_restore_old)
    recovery = tx.index("xr_vk_create_swapchain(width, height, VK_NULL_HANDLE)", failure_destroy_old)
    new_capture = tx.index("new_state = xr_vk_capture_swapchain_state()", recovery)
    success_restore_old = tx.index("xr_vk_restore_swapchain_state(old_state);", new_capture)
    success_destroy_old = tx.index("xr_vk_destroy_swapchain_resources();", success_restore_old)
    new_restore = tx.index("xr_vk_restore_swapchain_state(new_state);", success_destroy_old)
    if not (
        create < failure_destroy_partial < failure_restore_old < failure_destroy_old < recovery
        < new_capture < success_restore_old < success_destroy_old < new_restore
    ):
        raise RuntimeError("Transactional swapchain validation failed: unsafe retirement/recovery ordering")

    failure_branch = tx[create:new_capture]
    if "xr_vk_restore_swapchain_state(old_state);\n        return false;" in failure_branch:
        raise RuntimeError("Transactional swapchain validation failed: retired oldSwapchain can become active")

    print("[vulkan-swapchain-tx] oldSwapchain retirement-safe replacement + clean fallback recreation installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make RC6 Vulkan swapchain recreation retirement-safe and recoverable.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
