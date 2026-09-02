from __future__ import annotations

import argparse
from pathlib import Path


def _ordered(block: str, tokens: tuple[str, ...], label: str) -> None:
    positions = [block.find(token) for token in tokens]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise RuntimeError(f"{label}: missing or unsafe order: {tokens}")


def validate(root: Path) -> None:
    source = Path(root).resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    begin_start = text.find("bool xr_vk_bootstrap_begin_frame()")
    end_start = text.find("bool xr_vk_bootstrap_end_frame()", begin_start)
    wrapper_start = text.find("bool xr_vk_bootstrap_frame()", end_start)
    runtime_ready = text.find("bool xr_vk_bootstrap_runtime_ready()", wrapper_start)
    if min(begin_start, end_start, wrapper_start, runtime_ready) < 0 or not begin_start < end_start < wrapper_start < runtime_ready:
        raise RuntimeError("Vulkan runtime invariants: split frame lifecycle boundaries missing or reordered")

    begin = text[begin_start:end_start]
    end = text[end_start:wrapper_start]

    _ordered(
        begin,
        (
            "g_vkWaitForFences",
            "xr_vk_collect_deferred_textures()",
            "g_vkResetCommandBuffer",
            "g_vkAcquireNextImageKHR",
            "g_vkBeginCommandBuffer",
            "g_vkCmdBeginRenderPass",
        ),
        "Vulkan begin-frame fence/acquire/record ordering",
    )
    _ordered(
        end,
        (
            "g_vkCmdEndRenderPass",
            "g_vkEndCommandBuffer",
            "g_vkResetFences",
            "g_vkQueueSubmit",
            "VkResult presented = g_vkQueuePresentKHR",
        ),
        "Vulkan end-frame submit/present ordering",
    )

    present = end.find("VkResult presented = g_vkQueuePresentKHR")
    guard = end.find("presented != VK_SUCCESS && presented != VK_SUBOPTIMAL_KHR", present)
    commit = end.find("g_image_initialized[image_index] = 1", present)
    if min(present, guard, commit) < 0 or not present < guard < commit:
        raise RuntimeError("Vulkan runtime invariants: swapchain image state commits before successful/suboptimal present")

    acquire_ood = begin.find("acquire == VK_ERROR_OUT_OF_DATE_KHR")
    acquire_recreate = begin.find("xr_vk_recreate_swapchain_from_window()", acquire_ood)
    if min(acquire_ood, acquire_recreate) < 0 or not acquire_ood < acquire_recreate:
        raise RuntimeError("Vulkan runtime invariants: acquire OUT_OF_DATE recreation path incomplete")

    present_ood = end.find("presented == VK_ERROR_OUT_OF_DATE_KHR")
    present_recreate = end.find("xr_vk_recreate_swapchain_from_window()", present_ood)
    if min(present_ood, present_recreate) < 0 or not present_ood < present_recreate:
        raise RuntimeError("Vulkan runtime invariants: present OUT_OF_DATE recreation path incomplete")

    resize_start = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)")
    if resize_start < 0:
        raise RuntimeError("Vulkan runtime invariants: resize entry point missing")
    resize_end = begin_start
    resize_and_recreate = text[resize_start:resize_end]
    zero_guard = resize_and_recreate.find("if (!width || !height)")
    transaction = resize_and_recreate.find("xr_vk_transactional_recreate_swapchain(width, height)")
    if min(zero_guard, transaction) < 0 or not zero_guard < transaction:
        raise RuntimeError("Vulkan runtime invariants: zero-extent guard does not precede swapchain recreation")
    if resize_and_recreate.count("xr_vk_transactional_recreate_swapchain(width, height)") < 2:
        raise RuntimeError("Vulkan runtime invariants: not all resize paths are transactional")
    if "xr_vk_destroy_frame_resources();" in resize_and_recreate:
        raise RuntimeError("Vulkan runtime invariants: resize destroys persistent frame/material resources")
    if "xr_vk_destroy_swapchain_resources();\n    return xr_vk_create_swapchain(width, height);" in resize_and_recreate:
        raise RuntimeError("Vulkan runtime invariants: destructive legacy swapchain recreation remains")

    partial_start = text.find("void xr_vk_destroy_swapchain_resources()")
    full_start = text.find("void xr_vk_destroy_frame_resources()", partial_start)
    if partial_start < 0 or full_start < 0:
        raise RuntimeError("Vulkan runtime invariants: teardown boundaries missing")
    partial = text[partial_start:full_start]
    for forbidden in (
        "g_vkDestroyDescriptorPool",
        "g_vkDestroyDescriptorSetLayout",
        "g_vkDestroyPipelineLayout",
        "g_vkDestroyPipelineCache",
        "g_vkDestroySampler",
        "g_uniform_buffer",
        "g_upload_buffer",
        "g_stream_vertex_buffer",
        "g_stream_index_buffer",
    ):
        if forbidden in partial:
            raise RuntimeError(f"Vulkan runtime invariants: swapchain teardown owns persistent resource: {forbidden}")

    tx_start = text.find("bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)")
    if tx_start < 0 or tx_start >= resize_start:
        raise RuntimeError("Vulkan runtime invariants: transactional swapchain helper missing")
    tx = text[tx_start:resize_start]
    _ordered(
        tx,
        (
            "xr_vk_create_swapchain(width, height, old_state.swapchain)",
            "xr_vk_restore_swapchain_state(old_state);",
            "new_state = xr_vk_capture_swapchain_state()",
            "xr_vk_destroy_swapchain_resources();",
            "xr_vk_restore_swapchain_state(new_state);",
        ),
        "Vulkan transactional swapchain rollback/commit ordering",
    )

    destroy_start = full_start
    destroy_end = text.find("void xr_vk_destroy_window_runtime()", destroy_start)
    if destroy_end < 0:
        raise RuntimeError("Vulkan runtime invariants: frame teardown end marker missing")
    destroy_frame = text[destroy_start:destroy_end]
    idle = destroy_frame.find("g_vkDeviceWaitIdle")
    collect_shutdown = destroy_frame.find("xr_vk_collect_deferred_textures()", idle)
    if min(idle, collect_shutdown) < 0 or not idle < collect_shutdown:
        raise RuntimeError("Vulkan runtime invariants: deferred textures are not collected after device idle")

    print("[validate-vulkan-runtime] split begin/end frame + transactional swapchain + teardown lifetime invariants verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate split RC6 Vulkan frame/swapchain runtime invariants.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
