from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    required = (
        "bool xr_vk_create_swapchain(unsigned width, unsigned height, VkSwapchainKHR old_swapchain = VK_NULL_HANDLE)",
        "info.oldSwapchain = old_swapchain;",
        "struct xr_vk_swapchain_state",
        "bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)",
        "xr_vk_create_swapchain(width, height, old_state.swapchain)",
        "xr_vk_create_swapchain(width, height, VK_NULL_HANDLE)",
        "xr_vk_restore_swapchain_state(new_state);",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Transactional swapchain validation failed: missing {token}")

    tx_start = text.index("bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)")
    tx_end = text.index("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", tx_start)
    tx = text[tx_start:tx_end]

    wait_idle = tx.index("g_vkDeviceWaitIdle")
    capture_old = tx.index("old_state = xr_vk_capture_swapchain_state()")
    clear_old = tx.index("xr_vk_clear_swapchain_state_without_destroy()", capture_old)
    create_new = tx.index("xr_vk_create_swapchain(width, height, old_state.swapchain)", clear_old)
    destroy_partial = tx.index("xr_vk_destroy_swapchain_resources();", create_new)
    restore_retired_for_destroy = tx.index("xr_vk_restore_swapchain_state(old_state);", destroy_partial)
    destroy_retired = tx.index("xr_vk_destroy_swapchain_resources();", restore_retired_for_destroy)
    recovery = tx.index("xr_vk_create_swapchain(width, height, VK_NULL_HANDLE)", destroy_retired)
    capture_new = tx.index("new_state = xr_vk_capture_swapchain_state()", recovery)
    restore_old_for_destroy = tx.index("xr_vk_restore_swapchain_state(old_state);", capture_new)
    destroy_old = tx.index("xr_vk_destroy_swapchain_resources();", restore_old_for_destroy)
    restore_new = tx.index("xr_vk_restore_swapchain_state(new_state);", destroy_old)

    if not (
        wait_idle < capture_old < clear_old < create_new < destroy_partial
        < restore_retired_for_destroy < destroy_retired < recovery < capture_new
        < restore_old_for_destroy < destroy_old < restore_new
    ):
        raise RuntimeError("Transactional swapchain validation failed: retirement/recovery order is unsafe")

    failure_branch = tx[create_new:capture_new]
    forbidden_rollback = "xr_vk_restore_swapchain_state(old_state);\n        return false;"
    if forbidden_rollback in failure_branch:
        raise RuntimeError("Transactional swapchain validation failed: retired oldSwapchain can become active")
    if failure_branch.index("xr_vk_restore_swapchain_state(old_state);") > failure_branch.index("xr_vk_create_swapchain(width, height, VK_NULL_HANDLE)"):
        raise RuntimeError("Transactional swapchain validation failed: clean recovery happens before retired-state disposal")

    resize_start = tx_end
    frame_start = text.index("bool xr_vk_bootstrap_frame()", resize_start)
    recreate_segment = text[resize_start:frame_start]
    if recreate_segment.count("xr_vk_transactional_recreate_swapchain(width, height)") < 2:
        raise RuntimeError("Transactional swapchain validation failed: not all resize paths are transactional")
    if "xr_vk_destroy_swapchain_resources();\n    return xr_vk_create_swapchain(width, height);" in recreate_segment:
        raise RuntimeError("Transactional swapchain validation failed: legacy destructive recreate path remains")

    struct_start = text.index("struct xr_vk_swapchain_state")
    struct_end = text.index("};", struct_start)
    state_struct = text[struct_start:struct_end]
    for forbidden in (
        "descriptor_pool", "descriptor_set_layout", "pipeline_layout", "pipeline_cache",
        "default_sampler", "uniform_buffer", "upload_buffer", "stream_vertex_buffer", "stream_index_buffer",
    ):
        if forbidden in state_struct:
            raise RuntimeError(f"Transactional swapchain validation failed: persistent resource leaked into snapshot: {forbidden}")

    print("[vulkan-swapchain-tx-validator] retirement-safe oldSwapchain replacement/recovery invariants passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate retirement-safe Vulkan swapchain recreation invariants.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
