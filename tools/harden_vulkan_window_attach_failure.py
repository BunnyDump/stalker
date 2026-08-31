from __future__ import annotations

import argparse
from pathlib import Path


HELPER = r'''bool xr_vk_abort_window_attach()
{
    xr_vk_bootstrap_shutdown();
    return false;
}

'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    attach_start = text.find("bool xr_vk_bootstrap_attach_window(void* window_handle, unsigned width, unsigned height)")
    resize_start = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", attach_start)
    if attach_start < 0 or resize_start < 0:
        raise RuntimeError("Vulkan window attach hardening: attach/resize boundaries missing")

    if "bool xr_vk_abort_window_attach()" not in text:
        text = text[:attach_start] + HELPER + text[attach_start:]
        attach_start = text.find("bool xr_vk_bootstrap_attach_window(void* window_handle, unsigned width, unsigned height)")
        resize_start = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", attach_start)

    attach = text[attach_start:resize_start]

    attach = attach.replace(
        '''    if (!window_handle || !xr_vk_bootstrap_initialize())\n        return false;\n''',
        '''    if (!window_handle || !xr_vk_bootstrap_initialize())\n        return xr_vk_abort_window_attach();\n''',
    )
    attach = attach.replace(
        '''    if (!create_surface || !g_vkDestroySurfaceKHR || !g_vkGetPhysicalDeviceSurfaceSupportKHR ||\n        !g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR || !g_vkGetPhysicalDeviceSurfaceFormatsKHR || !g_vkGetPhysicalDeviceSurfacePresentModesKHR)\n        return false;\n''',
        '''    if (!create_surface || !g_vkDestroySurfaceKHR || !g_vkGetPhysicalDeviceSurfaceSupportKHR ||\n        !g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR || !g_vkGetPhysicalDeviceSurfaceFormatsKHR || !g_vkGetPhysicalDeviceSurfacePresentModesKHR)\n        return xr_vk_abort_window_attach();\n''',
    )
    attach = attach.replace(
        '''    if (create_surface(g_vulkan_instance, &surface_info, NULL, &g_surface) != VK_SUCCESS)\n        return false;\n''',
        '''    if (create_surface(g_vulkan_instance, &surface_info, NULL, &g_surface) != VK_SUCCESS)\n        return xr_vk_abort_window_attach();\n''',
    )

    attach = attach.replace(
        '''        xr_vk_destroy_window_runtime();\n        return false;\n''',
        '''        return xr_vk_abort_window_attach();\n''',
    )

    text = text[:attach_start] + attach + text[resize_start:]
    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    helper_start = final.find("bool xr_vk_abort_window_attach()")
    attach_start = final.find("bool xr_vk_bootstrap_attach_window(void* window_handle, unsigned width, unsigned height)", helper_start)
    resize_start = final.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", attach_start)
    if min(helper_start, attach_start, resize_start) < 0 or not helper_start < attach_start < resize_start:
        raise RuntimeError("Vulkan window attach hardening validation: helper/attach boundaries invalid")

    helper = final[helper_start:attach_start]
    attach = final[attach_start:resize_start]
    if "xr_vk_bootstrap_shutdown();" not in helper or "return false;" not in helper:
        raise RuntimeError("Vulkan window attach hardening validation: abort helper does not fully reset bootstrap")

    if "xr_vk_destroy_window_runtime();\n        return false;" in attach:
        raise RuntimeError("Vulkan window attach hardening validation: partial-only cleanup remains in attach failure path")

    required_failures = (
        "if (!window_handle || !xr_vk_bootstrap_initialize())",
        "if (!create_surface || !g_vkDestroySurfaceKHR",
        "if (create_surface(g_vulkan_instance, &surface_info, NULL, &g_surface) != VK_SUCCESS)",
        "if (g_present_queue_family == ~0u)",
        "if (create_device(g_selected_physical_device, &device_info, NULL, &g_device) != VK_SUCCESS)",
        "if (!xr_vk_load_device_functions())",
        "g_graphics_queue == VK_NULL_HANDLE || g_present_queue == VK_NULL_HANDLE",
    )
    for token in required_failures:
        pos = attach.find(token)
        if pos < 0:
            raise RuntimeError(f"Vulkan window attach hardening validation: failure site missing {token}")
        next_abort = attach.find("return xr_vk_abort_window_attach();", pos)
        next_success = attach.find("return true;", pos)
        if next_abort < 0 or (next_success >= 0 and next_success < next_abort):
            raise RuntimeError(f"Vulkan window attach hardening validation: failure site is not atomic {token}")

    if attach.count("return xr_vk_abort_window_attach();") < 7:
        raise RuntimeError("Vulkan window attach hardening validation: not all attach failures use full abort")

    print("[vulkan-window-attach] all HWND/device/surface attach failures fully reset Vulkan bootstrap state")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make Vulkan HWND attach failure-atomic and retry-safe.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
