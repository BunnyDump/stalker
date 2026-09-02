from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    old = '''    VkResult presented = g_vkQueuePresentKHR(g_present_queue, &present);
    g_image_initialized[image_index] = 1;
    return presented == VK_SUCCESS || presented == VK_SUBOPTIMAL_KHR;
'''
    new = '''    VkResult presented = g_vkQueuePresentKHR(g_present_queue, &present);
    if (presented != VK_SUCCESS && presented != VK_SUBOPTIMAL_KHR)
        return false;
    g_image_initialized[image_index] = 1;
    return true;
'''
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("Vulkan present-state hardening: present marker not found")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    frame_start = final.find("bool xr_vk_bootstrap_frame()")
    runtime_ready = final.find("bool xr_vk_bootstrap_runtime_ready()", frame_start)
    if frame_start < 0 or runtime_ready < 0:
        raise RuntimeError("Vulkan present-state hardening: frame function not found")
    frame = final[frame_start:runtime_ready]
    present_pos = frame.find("VkResult presented = g_vkQueuePresentKHR")
    result_guard = frame.find("presented != VK_SUCCESS && presented != VK_SUBOPTIMAL_KHR", present_pos)
    initialized_pos = frame.find("g_image_initialized[image_index] = 1", present_pos)
    if min(present_pos, result_guard, initialized_pos) < 0 or not present_pos < result_guard < initialized_pos:
        raise RuntimeError("Vulkan present-state hardening: image state can be committed before present succeeds")

    print("[vulkan-present] swapchain image state is committed only after successful/suboptimal present")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Vulkan swapchain image state tracking after present.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
