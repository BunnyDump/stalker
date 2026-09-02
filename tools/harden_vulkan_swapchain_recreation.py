from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    global_marker = "    VkExtent2D g_swapchain_extent = {0, 0};\n"
    if "g_window_handle" not in text:
        text = replace_once(
            text,
            global_marker,
            global_marker
            + "    HWND g_window_handle = NULL;\n"
            + "    unsigned g_requested_width = 0;\n"
            + "    unsigned g_requested_height = 0;\n",
            "swapchain window globals",
        )

    create_success = "        g_swapchain_format = chosen_format.format;\n        g_swapchain_extent = extent;\n"
    if "g_requested_width = width;" not in text:
        text = replace_once(
            text,
            create_success,
            create_success
            + "        g_requested_width = width;\n"
            + "        g_requested_height = height;\n",
            "swapchain requested extent tracking",
        )

    attach_surface = "    surface_info.hwnd = reinterpret_cast<HWND>(window_handle);\n"
    if "g_window_handle = reinterpret_cast<HWND>(window_handle);" not in text:
        text = replace_once(
            text,
            attach_surface,
            attach_surface + "    g_window_handle = reinterpret_cast<HWND>(window_handle);\n",
            "swapchain HWND tracking",
        )

    resize_old = '''bool xr_vk_bootstrap_resize(unsigned width, unsigned height)
{
    if (g_device == VK_NULL_HANDLE || g_surface == VK_NULL_HANDLE)
        return false;
    if (g_swapchain_extent.width == width && g_swapchain_extent.height == height)
        return true;
    xr_vk_destroy_frame_resources();
    return xr_vk_create_swapchain(width, height);
}
'''
    resize_new = '''bool xr_vk_bootstrap_resize(unsigned width, unsigned height)
{
    if (g_device == VK_NULL_HANDLE || g_surface == VK_NULL_HANDLE)
        return false;

    // A minimized Win32 window commonly reports a zero client extent. Keep the old
    // swapchain alive and defer recreation until a non-zero size is available.
    if (!width || !height)
        return true;
    if (g_swapchain != VK_NULL_HANDLE && g_requested_width == width && g_requested_height == height)
        return true;

    xr_vk_destroy_frame_resources();
    return xr_vk_create_swapchain(width, height);
}

bool xr_vk_recreate_swapchain_from_window()
{
    if (g_window_handle == NULL || g_device == VK_NULL_HANDLE || g_surface == VK_NULL_HANDLE)
        return false;

    RECT client = {};
    if (!GetClientRect(g_window_handle, &client))
        return false;
    const unsigned width = client.right > client.left ? unsigned(client.right - client.left) : 0;
    const unsigned height = client.bottom > client.top ? unsigned(client.bottom - client.top) : 0;
    if (!width || !height)
        return false;

    xr_vk_destroy_frame_resources();
    return xr_vk_create_swapchain(width, height);
}
'''
    if "bool xr_vk_recreate_swapchain_from_window()" not in text:
        text = replace_once(text, resize_old, resize_new, "swapchain resize lifecycle")

    acquire_old = '''    if (acquire == VK_ERROR_OUT_OF_DATE_KHR)
        return false;
    if (acquire != VK_SUCCESS && acquire != VK_SUBOPTIMAL_KHR)
        return false;
'''
    acquire_new = '''    if (acquire == VK_ERROR_OUT_OF_DATE_KHR)
    {
        xr_vk_recreate_swapchain_from_window();
        return false;
    }
    if (acquire != VK_SUCCESS && acquire != VK_SUBOPTIMAL_KHR)
        return false;
'''
    if "xr_vk_recreate_swapchain_from_window();\n        return false;" not in text:
        text = replace_once(text, acquire_old, acquire_new, "acquire out-of-date recreation")

    present_old = '''    if (presented != VK_SUCCESS && presented != VK_SUBOPTIMAL_KHR)
        return false;
    g_image_initialized[image_index] = 1;
    return true;
'''
    present_new = '''    if (presented == VK_ERROR_OUT_OF_DATE_KHR)
    {
        xr_vk_recreate_swapchain_from_window();
        return false;
    }
    if (presented != VK_SUCCESS && presented != VK_SUBOPTIMAL_KHR)
        return false;
    g_image_initialized[image_index] = 1;
    if (presented == VK_SUBOPTIMAL_KHR || acquire == VK_SUBOPTIMAL_KHR)
        xr_vk_recreate_swapchain_from_window();
    return true;
'''
    if "presented == VK_ERROR_OUT_OF_DATE_KHR" not in text:
        text = replace_once(text, present_old, present_new, "present out-of-date recreation")

    shutdown_marker = "        g_surface = VK_NULL_HANDLE;\n"
    if "g_window_handle = NULL;" not in text:
        text = replace_once(
            text,
            shutdown_marker,
            shutdown_marker
            + "        g_window_handle = NULL;\n"
            + "        g_requested_width = 0;\n"
            + "        g_requested_height = 0;\n",
            "swapchain window state reset",
        )

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "HWND g_window_handle = NULL",
        "g_requested_width = width",
        "if (!width || !height)",
        "bool xr_vk_recreate_swapchain_from_window()",
        "GetClientRect(g_window_handle, &client)",
        "acquire == VK_ERROR_OUT_OF_DATE_KHR",
        "presented == VK_ERROR_OUT_OF_DATE_KHR",
        "presented == VK_SUBOPTIMAL_KHR || acquire == VK_SUBOPTIMAL_KHR",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan swapchain hardening validation failed: missing {token}")

    print("[vulkan-swapchain] zero-extent-safe resize + Win32 OUT_OF_DATE/SUBOPTIMAL recreation verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Vulkan swapchain recreation across resize/minimize/Alt+Tab.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
