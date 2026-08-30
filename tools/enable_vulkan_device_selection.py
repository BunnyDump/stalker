from __future__ import annotations

import argparse
from pathlib import Path


def enable_device_selection(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    state_marker = "    unsigned g_physical_device_count = 0;\n"
    state_block = (
        state_marker +
        "    VkPhysicalDevice g_selected_physical_device = VK_NULL_HANDLE;\n" +
        "    unsigned g_graphics_queue_family = ~0u;\n"
    )
    if "g_selected_physical_device" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan device selection: bootstrap state marker not found")
        text = text.replace(state_marker, state_block, 1)

    reset_marker = "        g_physical_device_count = 0;\n"
    reset_block = (
        reset_marker +
        "        g_selected_physical_device = VK_NULL_HANDLE;\n" +
        "        g_graphics_queue_family = ~0u;\n"
    )
    reset_region = text[text.find("void xr_vk_bootstrap_reset"):text.find("void xr_vk_bootstrap_reset") + 800]
    if "g_graphics_queue_family = ~0u;" not in reset_region:
        if reset_marker not in text:
            raise RuntimeError("Vulkan device selection: reset marker not found")
        text = text.replace(reset_marker, reset_block, 1)

    old_enum = '''    if (!g_vkDestroyInstance || !enumerate_physical_devices ||\n        enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, NULL) != VK_SUCCESS ||\n        g_physical_device_count == 0)\n    {\n        xr_vk_bootstrap_shutdown();\n        return false;\n    }\n'''
    new_enum = '''    if (!g_vkDestroyInstance || !enumerate_physical_devices ||\n        enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, NULL) != VK_SUCCESS ||\n        g_physical_device_count == 0)\n    {\n        xr_vk_bootstrap_shutdown();\n        return false;\n    }\n\n    xr_vector<VkPhysicalDevice> devices(g_physical_device_count);\n    if (enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, &devices[0]) != VK_SUCCESS)\n    {\n        xr_vk_bootstrap_shutdown();\n        return false;\n    }\n\n    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_families =\n        reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(\n            g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceQueueFamilyProperties"));\n    if (!get_queue_families)\n    {\n        xr_vk_bootstrap_shutdown();\n        return false;\n    }\n\n    for (unsigned device_index = 0; device_index < g_physical_device_count && g_selected_physical_device == VK_NULL_HANDLE; ++device_index)\n    {\n        unsigned queue_count = 0;\n        get_queue_families(devices[device_index], &queue_count, NULL);\n        if (!queue_count)\n            continue;\n\n        xr_vector<VkQueueFamilyProperties> queues(queue_count);\n        get_queue_families(devices[device_index], &queue_count, &queues[0]);\n        for (unsigned queue_index = 0; queue_index < queue_count; ++queue_index)\n        {\n            if ((queues[queue_index].queueFlags & VK_QUEUE_GRAPHICS_BIT) && queues[queue_index].queueCount > 0)\n            {\n                g_selected_physical_device = devices[device_index];\n                g_graphics_queue_family = queue_index;\n                break;\n            }\n        }\n    }\n\n    if (g_selected_physical_device == VK_NULL_HANDLE || g_graphics_queue_family == ~0u)\n    {\n        xr_vk_bootstrap_shutdown();\n        return false;\n    }\n'''
    if "vkGetPhysicalDeviceQueueFamilyProperties" not in text:
        if old_enum not in text:
            raise RuntimeError("Vulkan device selection: physical-device enumeration block not found")
        text = text.replace(old_enum, new_enum, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    for token in (
        "vkGetPhysicalDeviceQueueFamilyProperties",
        "VK_QUEUE_GRAPHICS_BIT",
        "g_selected_physical_device",
        "g_graphics_queue_family",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan device selection validation failed: missing {token}")

    print("[vulkan-device] physical device and graphics queue family selection installed as private bootstrap state")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add Vulkan physical-device and graphics queue-family selection to xrRender_VK bootstrap.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable_device_selection(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
