from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkFormat g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;\n"
    state_block = state_marker + "    bool g_swapchain_create_invoked = false;\n"
    if "g_swapchain_create_invoked" not in text:
        if state_marker not in text:
            raise RuntimeError("Swapchain retirement boundary: preferred format state not materialized")
        text = text.replace(state_marker, state_block, 1)

    create_signature = "    bool xr_vk_create_swapchain(unsigned width, unsigned height, VkSwapchainKHR old_swapchain = VK_NULL_HANDLE)\n    {\n"
    create_begin = create_signature + "        g_swapchain_create_invoked = false;\n"
    if create_begin not in text:
        if create_signature not in text:
            raise RuntimeError("Swapchain retirement boundary: create signature not found")
        text = text.replace(create_signature, create_begin, 1)

    call_marker = "        if (g_vkCreateSwapchainKHR(g_device, &info, NULL, &g_swapchain) != VK_SUCCESS)\n"
    call_block = "        g_swapchain_create_invoked = true;\n" + call_marker
    if call_block not in text:
        if call_marker not in text:
            raise RuntimeError("Swapchain retirement boundary: vkCreateSwapchainKHR call not found")
        text = text.replace(call_marker, call_block, 1)

    tx_start = text.find("bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)")
    tx_end = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", tx_start)
    if tx_start < 0 or tx_end < 0:
        raise RuntimeError("Swapchain retirement boundary: recreation helper not found")
    tx = text[tx_start:tx_end]

    failure_marker = '''    if (!xr_vk_create_swapchain(width, height, old_state.swapchain))
    {
        xr_vk_destroy_swapchain_resources();
        xr_vk_clear_swapchain_state_without_destroy();

        xr_vk_restore_swapchain_state(old_state);
        xr_vk_destroy_swapchain_resources();
'''
    failure_replacement = '''    if (!xr_vk_create_swapchain(width, height, old_state.swapchain))
    {
        const bool old_swapchain_retired = g_swapchain_create_invoked;
        xr_vk_destroy_swapchain_resources();
        xr_vk_clear_swapchain_state_without_destroy();

        if (!old_swapchain_retired)
        {
            // Validation/surface/format selection failed before vkCreateSwapchainKHR.
            // The old swapchain was never retired and remains the valid active state.
            xr_vk_restore_swapchain_state(old_state);
            g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;
            return false;
        }

        xr_vk_restore_swapchain_state(old_state);
        xr_vk_destroy_swapchain_resources();
'''
    if "const bool old_swapchain_retired = g_swapchain_create_invoked;" not in tx:
        if failure_marker not in tx:
            raise RuntimeError("Swapchain retirement boundary: failure branch marker changed")
        tx = tx.replace(failure_marker, failure_replacement, 1)

    text = text[:tx_start] + tx + text[tx_end:]
    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "bool g_swapchain_create_invoked = false;",
        "g_swapchain_create_invoked = false;",
        "g_swapchain_create_invoked = true;",
        "const bool old_swapchain_retired = g_swapchain_create_invoked;",
        "if (!old_swapchain_retired)",
        "xr_vk_restore_swapchain_state(old_state);",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Swapchain retirement boundary validation failed: missing {token}")

    create_start = final.index(create_signature)
    create_end = final.index("bool xr_vk_transactional_recreate_swapchain", create_start)
    create_body = final[create_start:create_end]
    reset = create_body.index("g_swapchain_create_invoked = false;")
    invoke = create_body.index("g_swapchain_create_invoked = true;")
    call = create_body.index("g_vkCreateSwapchainKHR", invoke)
    if not reset < invoke < call:
        raise RuntimeError("Swapchain retirement boundary validation failed: invocation boundary order is unsafe")

    tx = final[final.index("bool xr_vk_transactional_recreate_swapchain"):final.index("bool xr_vk_bootstrap_resize")]
    retired_capture = tx.index("old_swapchain_retired = g_swapchain_create_invoked")
    precreate_guard = tx.index("if (!old_swapchain_retired)", retired_capture)
    restore_live = tx.index("xr_vk_restore_swapchain_state(old_state);", precreate_guard)
    return_live = tx.index("return false;", restore_live)
    destroy_retired = tx.index("xr_vk_destroy_swapchain_resources();", return_live)
    if not retired_capture < precreate_guard < restore_live < return_live < destroy_retired:
        raise RuntimeError("Swapchain retirement boundary validation failed: live/retired paths are conflated")

    print("[vulkan-swapchain-retire] pre-vkCreate failures preserve old state; post-call failures dispose retired state")


def main() -> int:
    parser = argparse.ArgumentParser(description="Track the exact Vulkan oldSwapchain retirement boundary.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
