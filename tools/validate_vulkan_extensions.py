from __future__ import annotations

import argparse
from pathlib import Path


def install_extension_validation(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    instance_marker = '''    PFN_vkCreateInstance create_instance = reinterpret_cast<PFN_vkCreateInstance>(g_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance"));
    if (!create_instance)
    {
        xr_vk_bootstrap_reset();
        return false;
    }
'''
    instance_replacement = r'''    PFN_vkCreateInstance create_instance = reinterpret_cast<PFN_vkCreateInstance>(g_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance"));
    PFN_vkEnumerateInstanceExtensionProperties enumerate_instance_extensions =
        reinterpret_cast<PFN_vkEnumerateInstanceExtensionProperties>(
            g_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties"));
    if (!create_instance || !enumerate_instance_extensions)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    unsigned instance_extension_count = 0;
    if (enumerate_instance_extensions(NULL, &instance_extension_count, NULL) != VK_SUCCESS || !instance_extension_count)
    {
        xr_vk_bootstrap_reset();
        return false;
    }
    xr_vector<VkExtensionProperties> instance_extension_properties(instance_extension_count);
    if (enumerate_instance_extensions(NULL, &instance_extension_count, &instance_extension_properties[0]) != VK_SUCCESS)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    bool has_surface = false;
    bool has_win32_surface = false;
    for (unsigned i = 0; i < instance_extension_count; ++i)
    {
        if (xr_strcmp(instance_extension_properties[i].extensionName, VK_KHR_SURFACE_EXTENSION_NAME) == 0)
            has_surface = true;
        else if (xr_strcmp(instance_extension_properties[i].extensionName, VK_KHR_WIN32_SURFACE_EXTENSION_NAME) == 0)
            has_win32_surface = true;
    }
    if (!has_surface || !has_win32_surface)
    {
        OutputDebugStringA("[X-Ray Vulkan] Required instance surface extensions are unavailable.\n");
        xr_vk_bootstrap_reset();
        return false;
    }
'''
    if "enumerate_instance_extensions" not in text:
        if instance_marker not in text:
            raise RuntimeError("Vulkan extension validation: create-instance marker not found")
        text = text.replace(instance_marker, instance_replacement, 1)

    probe_marker = '''bool xr_vk_bootstrap_probe()
{
    const bool was_initialized = g_vulkan_instance != VK_NULL_HANDLE;
    if (!xr_vk_bootstrap_initialize())
        return false;
    const bool available = g_selected_physical_device != VK_NULL_HANDLE && g_graphics_queue_family != ~0u;
    if (!was_initialized)
        xr_vk_bootstrap_shutdown();
    return available;
}
'''
    probe_replacement = r'''bool xr_vk_selected_device_supports_swapchain()
{
    if (g_vulkan_instance == VK_NULL_HANDLE || g_selected_physical_device == VK_NULL_HANDLE || !g_vkGetInstanceProcAddr)
        return false;

    PFN_vkEnumerateDeviceExtensionProperties enumerate_device_extensions =
        reinterpret_cast<PFN_vkEnumerateDeviceExtensionProperties>(
            g_vkGetInstanceProcAddr(g_vulkan_instance, "vkEnumerateDeviceExtensionProperties"));
    if (!enumerate_device_extensions)
        return false;

    unsigned device_extension_count = 0;
    if (enumerate_device_extensions(g_selected_physical_device, NULL, &device_extension_count, NULL) != VK_SUCCESS || !device_extension_count)
        return false;

    xr_vector<VkExtensionProperties> device_extension_properties(device_extension_count);
    if (enumerate_device_extensions(g_selected_physical_device, NULL, &device_extension_count, &device_extension_properties[0]) != VK_SUCCESS)
        return false;

    for (unsigned i = 0; i < device_extension_count; ++i)
    {
        if (xr_strcmp(device_extension_properties[i].extensionName, VK_KHR_SWAPCHAIN_EXTENSION_NAME) == 0)
            return true;
    }
    return false;
}

bool xr_vk_bootstrap_probe()
{
    const bool was_initialized = g_vulkan_instance != VK_NULL_HANDLE;
    if (!xr_vk_bootstrap_initialize())
        return false;
    const bool available =
        g_selected_physical_device != VK_NULL_HANDLE &&
        g_graphics_queue_family != ~0u &&
        xr_vk_selected_device_supports_swapchain();
    if (!available)
        OutputDebugStringA("[X-Ray Vulkan] Capability probe rejected selected device: VK_KHR_swapchain unavailable.\n");
    if (!was_initialized)
        xr_vk_bootstrap_shutdown();
    return available;
}
'''
    if "xr_vk_selected_device_supports_swapchain" not in text:
        if probe_marker not in text:
            raise RuntimeError("Vulkan extension validation: capability probe marker not found")
        text = text.replace(probe_marker, probe_replacement, 1)

    device_marker = '''    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_families = reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceQueueFamilyProperties"));
    PFN_vkCreateDevice create_device = reinterpret_cast<PFN_vkCreateDevice>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkCreateDevice"));
    if (!get_queue_families || !create_device)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }
'''
    device_replacement = r'''    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_families = reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceQueueFamilyProperties"));
    PFN_vkCreateDevice create_device = reinterpret_cast<PFN_vkCreateDevice>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkCreateDevice"));
    PFN_vkEnumerateDeviceExtensionProperties enumerate_device_extensions =
        reinterpret_cast<PFN_vkEnumerateDeviceExtensionProperties>(
            g_vkGetInstanceProcAddr(g_vulkan_instance, "vkEnumerateDeviceExtensionProperties"));
    if (!get_queue_families || !create_device || !enumerate_device_extensions)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }

    unsigned device_extension_count = 0;
    if (enumerate_device_extensions(g_selected_physical_device, NULL, &device_extension_count, NULL) != VK_SUCCESS || !device_extension_count)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }
    xr_vector<VkExtensionProperties> device_extension_properties(device_extension_count);
    if (enumerate_device_extensions(g_selected_physical_device, NULL, &device_extension_count, &device_extension_properties[0]) != VK_SUCCESS)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }
    bool has_swapchain = false;
    for (unsigned i = 0; i < device_extension_count; ++i)
    {
        if (xr_strcmp(device_extension_properties[i].extensionName, VK_KHR_SWAPCHAIN_EXTENSION_NAME) == 0)
        {
            has_swapchain = true;
            break;
        }
    }
    if (!has_swapchain)
    {
        OutputDebugStringA("[X-Ray Vulkan] VK_KHR_swapchain is unavailable on the selected device.\n");
        xr_vk_destroy_window_runtime();
        return false;
    }
'''
    if "bool has_swapchain = false;" not in text:
        if device_marker not in text:
            raise RuntimeError("Vulkan extension validation: create-device marker not found")
        text = text.replace(device_marker, device_replacement, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "vkEnumerateInstanceExtensionProperties",
        "VK_KHR_SURFACE_EXTENSION_NAME",
        "VK_KHR_WIN32_SURFACE_EXTENSION_NAME",
        "vkEnumerateDeviceExtensionProperties",
        "VK_KHR_SWAPCHAIN_EXTENSION_NAME",
        "bool xr_vk_selected_device_supports_swapchain()",
        "xr_vk_selected_device_supports_swapchain();",
        "Capability probe rejected selected device",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan extension validation failed: missing {token}")

    probe_start = final.find("bool xr_vk_bootstrap_probe()")
    attach_start = final.find("bool xr_vk_bootstrap_attach_window", probe_start)
    probe = final[probe_start:attach_start]
    if probe.find("xr_vk_selected_device_supports_swapchain()") < probe.find("g_graphics_queue_family != ~0u"):
        raise RuntimeError("Vulkan extension validation failed: swapchain capability gate ordering invalid")

    print("[vulkan-extensions] required instance extensions plus pre-activation VK_KHR_swapchain capability are validated")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate required Vulkan instance/device extensions before renderer activation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_extension_validation(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
