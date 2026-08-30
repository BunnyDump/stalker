from __future__ import annotations

import argparse
import re
from pathlib import Path

HEADER = r'''#pragma once

bool xr_vk_bootstrap_initialize();
bool xr_vk_bootstrap_probe();
bool xr_vk_bootstrap_attach_window(void* hwnd, unsigned width, unsigned height);
bool xr_vk_bootstrap_resize(unsigned width, unsigned height);
bool xr_vk_bootstrap_frame();
bool xr_vk_bootstrap_runtime_ready();
void xr_vk_bootstrap_shutdown();
unsigned xr_vk_bootstrap_physical_device_count();
'''

SOURCE = r'''#include "stdafx.h"
#define VK_NO_PROTOTYPES
#define VK_USE_PLATFORM_WIN32_KHR
#include "../../third-party/include/x64/vulkan/vulkan.h"
#include "vk_bootstrap.h"
#include <windows.h>

namespace
{
    HMODULE g_vulkan_loader = NULL;
    VkInstance g_vulkan_instance = VK_NULL_HANDLE;
    VkPhysicalDevice g_selected_physical_device = VK_NULL_HANDLE;
    unsigned g_physical_device_count = 0;
    unsigned g_graphics_queue_family = ~0u;
    unsigned g_present_queue_family = ~0u;

    VkDevice g_device = VK_NULL_HANDLE;
    VkQueue g_graphics_queue = VK_NULL_HANDLE;
    VkQueue g_present_queue = VK_NULL_HANDLE;
    VkSurfaceKHR g_surface = VK_NULL_HANDLE;
    VkSwapchainKHR g_swapchain = VK_NULL_HANDLE;
    VkFormat g_swapchain_format = VK_FORMAT_UNDEFINED;
    VkExtent2D g_swapchain_extent = {0, 0};
    VkCommandPool g_command_pool = VK_NULL_HANDLE;
    VkSemaphore g_image_available = VK_NULL_HANDLE;
    VkSemaphore g_render_finished = VK_NULL_HANDLE;
    VkFence g_frame_fence = VK_NULL_HANDLE;
    xr_vector<VkImage> g_swapchain_images;
    xr_vector<VkImageView> g_swapchain_views;
    xr_vector<VkCommandBuffer> g_command_buffers;
    xr_vector<u8> g_image_initialized;

    PFN_vkGetInstanceProcAddr g_vkGetInstanceProcAddr = NULL;
    PFN_vkGetDeviceProcAddr g_vkGetDeviceProcAddr = NULL;
    PFN_vkDestroyInstance g_vkDestroyInstance = NULL;
    PFN_vkDestroySurfaceKHR g_vkDestroySurfaceKHR = NULL;
    PFN_vkGetPhysicalDeviceSurfaceSupportKHR g_vkGetPhysicalDeviceSurfaceSupportKHR = NULL;
    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR = NULL;
    PFN_vkGetPhysicalDeviceSurfaceFormatsKHR g_vkGetPhysicalDeviceSurfaceFormatsKHR = NULL;
    PFN_vkGetPhysicalDeviceSurfacePresentModesKHR g_vkGetPhysicalDeviceSurfacePresentModesKHR = NULL;

    PFN_vkDestroyDevice g_vkDestroyDevice = NULL;
    PFN_vkGetDeviceQueue g_vkGetDeviceQueue = NULL;
    PFN_vkCreateSwapchainKHR g_vkCreateSwapchainKHR = NULL;
    PFN_vkDestroySwapchainKHR g_vkDestroySwapchainKHR = NULL;
    PFN_vkGetSwapchainImagesKHR g_vkGetSwapchainImagesKHR = NULL;
    PFN_vkCreateImageView g_vkCreateImageView = NULL;
    PFN_vkDestroyImageView g_vkDestroyImageView = NULL;
    PFN_vkCreateCommandPool g_vkCreateCommandPool = NULL;
    PFN_vkDestroyCommandPool g_vkDestroyCommandPool = NULL;
    PFN_vkAllocateCommandBuffers g_vkAllocateCommandBuffers = NULL;
    PFN_vkResetCommandBuffer g_vkResetCommandBuffer = NULL;
    PFN_vkBeginCommandBuffer g_vkBeginCommandBuffer = NULL;
    PFN_vkEndCommandBuffer g_vkEndCommandBuffer = NULL;
    PFN_vkCmdPipelineBarrier g_vkCmdPipelineBarrier = NULL;
    PFN_vkCmdClearColorImage g_vkCmdClearColorImage = NULL;
    PFN_vkCreateSemaphore g_vkCreateSemaphore = NULL;
    PFN_vkDestroySemaphore g_vkDestroySemaphore = NULL;
    PFN_vkCreateFence g_vkCreateFence = NULL;
    PFN_vkDestroyFence g_vkDestroyFence = NULL;
    PFN_vkWaitForFences g_vkWaitForFences = NULL;
    PFN_vkResetFences g_vkResetFences = NULL;
    PFN_vkAcquireNextImageKHR g_vkAcquireNextImageKHR = NULL;
    PFN_vkQueueSubmit g_vkQueueSubmit = NULL;
    PFN_vkQueuePresentKHR g_vkQueuePresentKHR = NULL;
    PFN_vkDeviceWaitIdle g_vkDeviceWaitIdle = NULL;

    unsigned xr_vk_clamp_u32(unsigned value, unsigned minimum, unsigned maximum)
    {
        if (value < minimum) return minimum;
        if (maximum && value > maximum) return maximum;
        return value;
    }

    void xr_vk_clear_device_function_table()
    {
        g_vkDestroyDevice = NULL;
        g_vkGetDeviceQueue = NULL;
        g_vkCreateSwapchainKHR = NULL;
        g_vkDestroySwapchainKHR = NULL;
        g_vkGetSwapchainImagesKHR = NULL;
        g_vkCreateImageView = NULL;
        g_vkDestroyImageView = NULL;
        g_vkCreateCommandPool = NULL;
        g_vkDestroyCommandPool = NULL;
        g_vkAllocateCommandBuffers = NULL;
        g_vkResetCommandBuffer = NULL;
        g_vkBeginCommandBuffer = NULL;
        g_vkEndCommandBuffer = NULL;
        g_vkCmdPipelineBarrier = NULL;
        g_vkCmdClearColorImage = NULL;
        g_vkCreateSemaphore = NULL;
        g_vkDestroySemaphore = NULL;
        g_vkCreateFence = NULL;
        g_vkDestroyFence = NULL;
        g_vkWaitForFences = NULL;
        g_vkResetFences = NULL;
        g_vkAcquireNextImageKHR = NULL;
        g_vkQueueSubmit = NULL;
        g_vkQueuePresentKHR = NULL;
        g_vkDeviceWaitIdle = NULL;
    }

    void xr_vk_destroy_frame_resources()
    {
        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);

        if (g_device != VK_NULL_HANDLE && g_vkDestroyFence && g_frame_fence != VK_NULL_HANDLE)
            g_vkDestroyFence(g_device, g_frame_fence, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroySemaphore && g_render_finished != VK_NULL_HANDLE)
            g_vkDestroySemaphore(g_device, g_render_finished, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroySemaphore && g_image_available != VK_NULL_HANDLE)
            g_vkDestroySemaphore(g_device, g_image_available, NULL);
        g_frame_fence = VK_NULL_HANDLE;
        g_render_finished = VK_NULL_HANDLE;
        g_image_available = VK_NULL_HANDLE;

        if (g_device != VK_NULL_HANDLE && g_vkDestroyCommandPool && g_command_pool != VK_NULL_HANDLE)
            g_vkDestroyCommandPool(g_device, g_command_pool, NULL);
        g_command_pool = VK_NULL_HANDLE;
        g_command_buffers.clear();

        if (g_device != VK_NULL_HANDLE && g_vkDestroyImageView)
        {
            for (u32 i = 0; i < g_swapchain_views.size(); ++i)
                if (g_swapchain_views[i] != VK_NULL_HANDLE)
                    g_vkDestroyImageView(g_device, g_swapchain_views[i], NULL);
        }
        g_swapchain_views.clear();
        g_swapchain_images.clear();
        g_image_initialized.clear();

        if (g_device != VK_NULL_HANDLE && g_vkDestroySwapchainKHR && g_swapchain != VK_NULL_HANDLE)
            g_vkDestroySwapchainKHR(g_device, g_swapchain, NULL);
        g_swapchain = VK_NULL_HANDLE;
        g_swapchain_format = VK_FORMAT_UNDEFINED;
        g_swapchain_extent.width = 0;
        g_swapchain_extent.height = 0;
    }

    void xr_vk_destroy_window_runtime()
    {
        xr_vk_destroy_frame_resources();

        if (g_device != VK_NULL_HANDLE && g_vkDestroyDevice)
            g_vkDestroyDevice(g_device, NULL);
        g_device = VK_NULL_HANDLE;
        g_graphics_queue = VK_NULL_HANDLE;
        g_present_queue = VK_NULL_HANDLE;
        g_present_queue_family = ~0u;
        xr_vk_clear_device_function_table();

        if (g_vulkan_instance != VK_NULL_HANDLE && g_surface != VK_NULL_HANDLE && g_vkDestroySurfaceKHR)
            g_vkDestroySurfaceKHR(g_vulkan_instance, g_surface, NULL);
        g_surface = VK_NULL_HANDLE;
    }

    void xr_vk_bootstrap_reset()
    {
        g_vulkan_instance = VK_NULL_HANDLE;
        g_selected_physical_device = VK_NULL_HANDLE;
        g_physical_device_count = 0;
        g_graphics_queue_family = ~0u;
        g_present_queue_family = ~0u;
        g_vkGetInstanceProcAddr = NULL;
        g_vkGetDeviceProcAddr = NULL;
        g_vkDestroyInstance = NULL;
        g_vkDestroySurfaceKHR = NULL;
        g_vkGetPhysicalDeviceSurfaceSupportKHR = NULL;
        g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR = NULL;
        g_vkGetPhysicalDeviceSurfaceFormatsKHR = NULL;
        g_vkGetPhysicalDeviceSurfacePresentModesKHR = NULL;
        xr_vk_clear_device_function_table();
        if (g_vulkan_loader)
        {
            FreeLibrary(g_vulkan_loader);
            g_vulkan_loader = NULL;
        }
    }

    bool xr_vk_load_device_functions()
    {
#define XR_VK_LOAD_DEVICE(name) \
        g_##name = reinterpret_cast<PFN_##name>(g_vkGetDeviceProcAddr(g_device, #name)); \
        if (!g_##name) return false
        XR_VK_LOAD_DEVICE(vkDestroyDevice);
        XR_VK_LOAD_DEVICE(vkGetDeviceQueue);
        XR_VK_LOAD_DEVICE(vkCreateSwapchainKHR);
        XR_VK_LOAD_DEVICE(vkDestroySwapchainKHR);
        XR_VK_LOAD_DEVICE(vkGetSwapchainImagesKHR);
        XR_VK_LOAD_DEVICE(vkCreateImageView);
        XR_VK_LOAD_DEVICE(vkDestroyImageView);
        XR_VK_LOAD_DEVICE(vkCreateCommandPool);
        XR_VK_LOAD_DEVICE(vkDestroyCommandPool);
        XR_VK_LOAD_DEVICE(vkAllocateCommandBuffers);
        XR_VK_LOAD_DEVICE(vkResetCommandBuffer);
        XR_VK_LOAD_DEVICE(vkBeginCommandBuffer);
        XR_VK_LOAD_DEVICE(vkEndCommandBuffer);
        XR_VK_LOAD_DEVICE(vkCmdPipelineBarrier);
        XR_VK_LOAD_DEVICE(vkCmdClearColorImage);
        XR_VK_LOAD_DEVICE(vkCreateSemaphore);
        XR_VK_LOAD_DEVICE(vkDestroySemaphore);
        XR_VK_LOAD_DEVICE(vkCreateFence);
        XR_VK_LOAD_DEVICE(vkDestroyFence);
        XR_VK_LOAD_DEVICE(vkWaitForFences);
        XR_VK_LOAD_DEVICE(vkResetFences);
        XR_VK_LOAD_DEVICE(vkAcquireNextImageKHR);
        XR_VK_LOAD_DEVICE(vkQueueSubmit);
        XR_VK_LOAD_DEVICE(vkQueuePresentKHR);
        XR_VK_LOAD_DEVICE(vkDeviceWaitIdle);
#undef XR_VK_LOAD_DEVICE
        return true;
    }

    bool xr_vk_create_swapchain(unsigned width, unsigned height)
    {
        VkSurfaceCapabilitiesKHR caps = {};
        if (g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR(g_selected_physical_device, g_surface, &caps) != VK_SUCCESS)
            return false;

        unsigned format_count = 0;
        if (g_vkGetPhysicalDeviceSurfaceFormatsKHR(g_selected_physical_device, g_surface, &format_count, NULL) != VK_SUCCESS || !format_count)
            return false;
        xr_vector<VkSurfaceFormatKHR> formats(format_count);
        if (g_vkGetPhysicalDeviceSurfaceFormatsKHR(g_selected_physical_device, g_surface, &format_count, &formats[0]) != VK_SUCCESS)
            return false;

        VkSurfaceFormatKHR chosen_format = formats[0];
        if (format_count == 1 && formats[0].format == VK_FORMAT_UNDEFINED)
        {
            chosen_format.format = VK_FORMAT_B8G8R8A8_UNORM;
            chosen_format.colorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
        }
        else
        {
            for (unsigned i = 0; i < format_count; ++i)
            {
                if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM && formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                {
                    chosen_format = formats[i];
                    break;
                }
            }
        }

        unsigned present_mode_count = 0;
        if (g_vkGetPhysicalDeviceSurfacePresentModesKHR(g_selected_physical_device, g_surface, &present_mode_count, NULL) != VK_SUCCESS || !present_mode_count)
            return false;
        xr_vector<VkPresentModeKHR> present_modes(present_mode_count);
        if (g_vkGetPhysicalDeviceSurfacePresentModesKHR(g_selected_physical_device, g_surface, &present_mode_count, &present_modes[0]) != VK_SUCCESS)
            return false;
        VkPresentModeKHR present_mode = VK_PRESENT_MODE_FIFO_KHR;
        for (unsigned i = 0; i < present_mode_count; ++i)
            if (present_modes[i] == VK_PRESENT_MODE_MAILBOX_KHR)
                present_mode = VK_PRESENT_MODE_MAILBOX_KHR;

        VkExtent2D extent = caps.currentExtent;
        if (caps.currentExtent.width == 0xffffffffu)
        {
            extent.width = xr_vk_clamp_u32(width, caps.minImageExtent.width, caps.maxImageExtent.width);
            extent.height = xr_vk_clamp_u32(height, caps.minImageExtent.height, caps.maxImageExtent.height);
        }
        if (!extent.width || !extent.height)
            return false;

        unsigned image_count = caps.minImageCount + 1;
        if (caps.maxImageCount && image_count > caps.maxImageCount)
            image_count = caps.maxImageCount;

        VkCompositeAlphaFlagBitsKHR composite_alpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        if (!(caps.supportedCompositeAlpha & composite_alpha))
        {
            const VkCompositeAlphaFlagBitsKHR candidates[] = {
                VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,
                VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR,
                VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR};
            for (u32 i = 0; i < sizeof(candidates) / sizeof(candidates[0]); ++i)
                if (caps.supportedCompositeAlpha & candidates[i]) { composite_alpha = candidates[i]; break; }
        }

        unsigned queue_indices[2] = {g_graphics_queue_family, g_present_queue_family};
        VkSwapchainCreateInfoKHR info = {};
        info.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
        info.surface = g_surface;
        info.minImageCount = image_count;
        info.imageFormat = chosen_format.format;
        info.imageColorSpace = chosen_format.colorSpace;
        info.imageExtent = extent;
        info.imageArrayLayers = 1;
        info.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
        if (g_graphics_queue_family != g_present_queue_family)
        {
            info.imageSharingMode = VK_SHARING_MODE_CONCURRENT;
            info.queueFamilyIndexCount = 2;
            info.pQueueFamilyIndices = queue_indices;
        }
        else
            info.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
        info.preTransform = caps.currentTransform;
        info.compositeAlpha = composite_alpha;
        info.presentMode = present_mode;
        info.clipped = VK_TRUE;
        info.oldSwapchain = VK_NULL_HANDLE;

        if (g_vkCreateSwapchainKHR(g_device, &info, NULL, &g_swapchain) != VK_SUCCESS)
            return false;
        g_swapchain_format = chosen_format.format;
        g_swapchain_extent = extent;

        unsigned actual_count = 0;
        if (g_vkGetSwapchainImagesKHR(g_device, g_swapchain, &actual_count, NULL) != VK_SUCCESS || !actual_count)
            return false;
        g_swapchain_images.resize(actual_count);
        if (g_vkGetSwapchainImagesKHR(g_device, g_swapchain, &actual_count, &g_swapchain_images[0]) != VK_SUCCESS)
            return false;
        g_image_initialized.assign(actual_count, 0);

        g_swapchain_views.assign(actual_count, VK_NULL_HANDLE);
        for (unsigned i = 0; i < actual_count; ++i)
        {
            VkImageViewCreateInfo view_info = {};
            view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
            view_info.image = g_swapchain_images[i];
            view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
            view_info.format = g_swapchain_format;
            view_info.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
            view_info.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
            view_info.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
            view_info.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
            view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
            view_info.subresourceRange.levelCount = 1;
            view_info.subresourceRange.layerCount = 1;
            if (g_vkCreateImageView(g_device, &view_info, NULL, &g_swapchain_views[i]) != VK_SUCCESS)
                return false;
        }

        VkCommandPoolCreateInfo pool_info = {};
        pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = g_graphics_queue_family;
        if (g_vkCreateCommandPool(g_device, &pool_info, NULL, &g_command_pool) != VK_SUCCESS)
            return false;

        g_command_buffers.resize(actual_count);
        VkCommandBufferAllocateInfo command_info = {};
        command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        command_info.commandPool = g_command_pool;
        command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command_info.commandBufferCount = actual_count;
        if (g_vkAllocateCommandBuffers(g_device, &command_info, &g_command_buffers[0]) != VK_SUCCESS)
            return false;

        VkSemaphoreCreateInfo semaphore_info = {};
        semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        if (g_vkCreateSemaphore(g_device, &semaphore_info, NULL, &g_image_available) != VK_SUCCESS ||
            g_vkCreateSemaphore(g_device, &semaphore_info, NULL, &g_render_finished) != VK_SUCCESS)
            return false;

        VkFenceCreateInfo fence_info = {};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        if (g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) != VK_SUCCESS)
            return false;

        return true;
    }
}

bool xr_vk_bootstrap_initialize()
{
    if (g_vulkan_instance != VK_NULL_HANDLE)
        return true;

    g_vulkan_loader = LoadLibraryA("vulkan-1.dll");
    if (!g_vulkan_loader)
        return false;

    g_vkGetInstanceProcAddr = reinterpret_cast<PFN_vkGetInstanceProcAddr>(GetProcAddress(g_vulkan_loader, "vkGetInstanceProcAddr"));
    if (!g_vkGetInstanceProcAddr)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    PFN_vkCreateInstance create_instance = reinterpret_cast<PFN_vkCreateInstance>(g_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance"));
    if (!create_instance)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    VkApplicationInfo app_info = {};
    app_info.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app_info.pApplicationName = "S.T.A.L.K.E.R. X-Ray RC6";
    app_info.applicationVersion = VK_MAKE_VERSION(0, 6, 0);
    app_info.pEngineName = "X-Ray Engine";
    app_info.engineVersion = VK_MAKE_VERSION(0, 6, 0);
    app_info.apiVersion = VK_API_VERSION_1_0;

    const char* instance_extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_WIN32_SURFACE_EXTENSION_NAME};
    VkInstanceCreateInfo instance_info = {};
    instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    instance_info.pApplicationInfo = &app_info;
    instance_info.enabledExtensionCount = 2;
    instance_info.ppEnabledExtensionNames = instance_extensions;

    if (create_instance(&instance_info, NULL, &g_vulkan_instance) != VK_SUCCESS)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    g_vkDestroyInstance = reinterpret_cast<PFN_vkDestroyInstance>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkDestroyInstance"));
    g_vkGetDeviceProcAddr = reinterpret_cast<PFN_vkGetDeviceProcAddr>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetDeviceProcAddr"));
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkEnumeratePhysicalDevices"));
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_families = reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceQueueFamilyProperties"));

    if (!g_vkDestroyInstance || !g_vkGetDeviceProcAddr || !enumerate_physical_devices || !get_queue_families ||
        enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, NULL) != VK_SUCCESS || !g_physical_device_count)
    {
        xr_vk_bootstrap_shutdown();
        return false;
    }

    xr_vector<VkPhysicalDevice> devices(g_physical_device_count);
    if (enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, &devices[0]) != VK_SUCCESS)
    {
        xr_vk_bootstrap_shutdown();
        return false;
    }

    for (unsigned device_index = 0; device_index < g_physical_device_count && g_selected_physical_device == VK_NULL_HANDLE; ++device_index)
    {
        unsigned queue_count = 0;
        get_queue_families(devices[device_index], &queue_count, NULL);
        if (!queue_count) continue;
        xr_vector<VkQueueFamilyProperties> queues(queue_count);
        get_queue_families(devices[device_index], &queue_count, &queues[0]);
        for (unsigned queue_index = 0; queue_index < queue_count; ++queue_index)
        {
            if ((queues[queue_index].queueFlags & VK_QUEUE_GRAPHICS_BIT) && queues[queue_index].queueCount)
            {
                g_selected_physical_device = devices[device_index];
                g_graphics_queue_family = queue_index;
                break;
            }
        }
    }

    if (g_selected_physical_device == VK_NULL_HANDLE || g_graphics_queue_family == ~0u)
    {
        xr_vk_bootstrap_shutdown();
        return false;
    }

    OutputDebugStringA("[X-Ray Vulkan] VkInstance initialized; graphics-capable physical device selected.\n");
    return true;
}

bool xr_vk_bootstrap_probe()
{
    const bool was_initialized = g_vulkan_instance != VK_NULL_HANDLE;
    if (!xr_vk_bootstrap_initialize())
        return false;
    const bool available = g_selected_physical_device != VK_NULL_HANDLE && g_graphics_queue_family != ~0u;
    if (!was_initialized)
        xr_vk_bootstrap_shutdown();
    return available;
}

bool xr_vk_bootstrap_attach_window(void* window_handle, unsigned width, unsigned height)
{
    if (g_device != VK_NULL_HANDLE && g_surface != VK_NULL_HANDLE && g_swapchain != VK_NULL_HANDLE)
        return true;
    if (!window_handle || !xr_vk_bootstrap_initialize())
        return false;

    PFN_vkCreateWin32SurfaceKHR create_surface = reinterpret_cast<PFN_vkCreateWin32SurfaceKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkCreateWin32SurfaceKHR"));
    g_vkDestroySurfaceKHR = reinterpret_cast<PFN_vkDestroySurfaceKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkDestroySurfaceKHR"));
    g_vkGetPhysicalDeviceSurfaceSupportKHR = reinterpret_cast<PFN_vkGetPhysicalDeviceSurfaceSupportKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceSurfaceSupportKHR"));
    g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR = reinterpret_cast<PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR"));
    g_vkGetPhysicalDeviceSurfaceFormatsKHR = reinterpret_cast<PFN_vkGetPhysicalDeviceSurfaceFormatsKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceSurfaceFormatsKHR"));
    g_vkGetPhysicalDeviceSurfacePresentModesKHR = reinterpret_cast<PFN_vkGetPhysicalDeviceSurfacePresentModesKHR>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceSurfacePresentModesKHR"));
    if (!create_surface || !g_vkDestroySurfaceKHR || !g_vkGetPhysicalDeviceSurfaceSupportKHR ||
        !g_vkGetPhysicalDeviceSurfaceCapabilitiesKHR || !g_vkGetPhysicalDeviceSurfaceFormatsKHR || !g_vkGetPhysicalDeviceSurfacePresentModesKHR)
        return false;

    VkWin32SurfaceCreateInfoKHR surface_info = {};
    surface_info.sType = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR;
    surface_info.hinstance = GetModuleHandle(NULL);
    surface_info.hwnd = reinterpret_cast<HWND>(window_handle);
    if (create_surface(g_vulkan_instance, &surface_info, NULL, &g_surface) != VK_SUCCESS)
        return false;

    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queue_families = reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceQueueFamilyProperties"));
    PFN_vkCreateDevice create_device = reinterpret_cast<PFN_vkCreateDevice>(g_vkGetInstanceProcAddr(g_vulkan_instance, "vkCreateDevice"));
    if (!get_queue_families || !create_device)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }

    unsigned queue_count = 0;
    get_queue_families(g_selected_physical_device, &queue_count, NULL);
    for (unsigned queue_index = 0; queue_index < queue_count; ++queue_index)
    {
        VkBool32 supported = VK_FALSE;
        if (g_vkGetPhysicalDeviceSurfaceSupportKHR(g_selected_physical_device, queue_index, g_surface, &supported) == VK_SUCCESS && supported)
        {
            g_present_queue_family = queue_index;
            break;
        }
    }
    if (g_present_queue_family == ~0u)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }

    const float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_infos[2] = {};
    unsigned queue_info_count = 1;
    queue_infos[0].sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queue_infos[0].queueFamilyIndex = g_graphics_queue_family;
    queue_infos[0].queueCount = 1;
    queue_infos[0].pQueuePriorities = &priority;
    if (g_present_queue_family != g_graphics_queue_family)
    {
        queue_info_count = 2;
        queue_infos[1].sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_infos[1].queueFamilyIndex = g_present_queue_family;
        queue_infos[1].queueCount = 1;
        queue_infos[1].pQueuePriorities = &priority;
    }

    const char* device_extensions[] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
    VkDeviceCreateInfo device_info = {};
    device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    device_info.queueCreateInfoCount = queue_info_count;
    device_info.pQueueCreateInfos = queue_infos;
    device_info.enabledExtensionCount = 1;
    device_info.ppEnabledExtensionNames = device_extensions;
    if (create_device(g_selected_physical_device, &device_info, NULL, &g_device) != VK_SUCCESS)
    {
        xr_vk_destroy_window_runtime();
        return false;
    }

    if (!xr_vk_load_device_functions())
    {
        xr_vk_destroy_window_runtime();
        return false;
    }
    g_vkGetDeviceQueue(g_device, g_graphics_queue_family, 0, &g_graphics_queue);
    g_vkGetDeviceQueue(g_device, g_present_queue_family, 0, &g_present_queue);
    if (g_graphics_queue == VK_NULL_HANDLE || g_present_queue == VK_NULL_HANDLE || !xr_vk_create_swapchain(width, height))
    {
        xr_vk_destroy_window_runtime();
        return false;
    }

    OutputDebugStringA("[X-Ray Vulkan] VkDevice, queues, Win32 surface, swapchain, command buffers and sync objects initialized.\n");
    return true;
}

bool xr_vk_bootstrap_resize(unsigned width, unsigned height)
{
    if (g_device == VK_NULL_HANDLE || g_surface == VK_NULL_HANDLE)
        return false;
    if (g_swapchain_extent.width == width && g_swapchain_extent.height == height)
        return true;
    xr_vk_destroy_frame_resources();
    return xr_vk_create_swapchain(width, height);
}

bool xr_vk_bootstrap_frame()
{
    if (!xr_vk_bootstrap_runtime_ready())
        return false;

    if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
        return false;

    unsigned image_index = 0;
    VkResult acquire = g_vkAcquireNextImageKHR(g_device, g_swapchain, ~0ull, g_image_available, VK_NULL_HANDLE, &image_index);
    if (acquire == VK_ERROR_OUT_OF_DATE_KHR)
        return false;
    if (acquire != VK_SUCCESS && acquire != VK_SUBOPTIMAL_KHR)
        return false;
    if (image_index >= g_command_buffers.size())
        return false;

    if (g_vkResetFences(g_device, 1, &g_frame_fence) != VK_SUCCESS ||
        g_vkResetCommandBuffer(g_command_buffers[image_index], 0) != VK_SUCCESS)
        return false;

    VkCommandBufferBeginInfo begin_info = {};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    begin_info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    if (g_vkBeginCommandBuffer(g_command_buffers[image_index], &begin_info) != VK_SUCCESS)
        return false;

    VkImageMemoryBarrier to_transfer = {};
    to_transfer.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    to_transfer.srcAccessMask = 0;
    to_transfer.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_transfer.oldLayout = g_image_initialized[image_index] ? VK_IMAGE_LAYOUT_PRESENT_SRC_KHR : VK_IMAGE_LAYOUT_UNDEFINED;
    to_transfer.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_transfer.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_transfer.image = g_swapchain_images[image_index];
    to_transfer.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    to_transfer.subresourceRange.levelCount = 1;
    to_transfer.subresourceRange.layerCount = 1;
    g_vkCmdPipelineBarrier(g_command_buffers[image_index], VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
        0, 0, NULL, 0, NULL, 1, &to_transfer);

    VkClearColorValue clear_color = {};
    clear_color.float32[0] = 0.015f;
    clear_color.float32[1] = 0.025f;
    clear_color.float32[2] = 0.040f;
    clear_color.float32[3] = 1.0f;
    VkImageSubresourceRange clear_range = {};
    clear_range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    clear_range.levelCount = 1;
    clear_range.layerCount = 1;
    g_vkCmdClearColorImage(g_command_buffers[image_index], g_swapchain_images[image_index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        &clear_color, 1, &clear_range);

    VkImageMemoryBarrier to_present = to_transfer;
    to_present.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    to_present.dstAccessMask = 0;
    to_present.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    to_present.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    g_vkCmdPipelineBarrier(g_command_buffers[image_index], VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
        0, 0, NULL, 0, NULL, 1, &to_present);

    if (g_vkEndCommandBuffer(g_command_buffers[image_index]) != VK_SUCCESS)
        return false;

    const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    VkSubmitInfo submit = {};
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit.waitSemaphoreCount = 1;
    submit.pWaitSemaphores = &g_image_available;
    submit.pWaitDstStageMask = &wait_stage;
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &g_command_buffers[image_index];
    submit.signalSemaphoreCount = 1;
    submit.pSignalSemaphores = &g_render_finished;
    if (g_vkQueueSubmit(g_graphics_queue, 1, &submit, g_frame_fence) != VK_SUCCESS)
        return false;

    VkPresentInfoKHR present = {};
    present.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    present.waitSemaphoreCount = 1;
    present.pWaitSemaphores = &g_render_finished;
    present.swapchainCount = 1;
    present.pSwapchains = &g_swapchain;
    present.pImageIndices = &image_index;
    VkResult presented = g_vkQueuePresentKHR(g_present_queue, &present);
    g_image_initialized[image_index] = 1;
    return presented == VK_SUCCESS || presented == VK_SUBOPTIMAL_KHR;
}

bool xr_vk_bootstrap_runtime_ready()
{
    return g_vulkan_instance != VK_NULL_HANDLE && g_selected_physical_device != VK_NULL_HANDLE &&
        g_device != VK_NULL_HANDLE && g_graphics_queue != VK_NULL_HANDLE && g_present_queue != VK_NULL_HANDLE &&
        g_surface != VK_NULL_HANDLE && g_swapchain != VK_NULL_HANDLE && !g_command_buffers.empty() &&
        g_image_available != VK_NULL_HANDLE && g_render_finished != VK_NULL_HANDLE && g_frame_fence != VK_NULL_HANDLE;
}

void xr_vk_bootstrap_shutdown()
{
    xr_vk_destroy_window_runtime();
    if (g_vulkan_instance != VK_NULL_HANDLE && g_vkDestroyInstance)
        g_vkDestroyInstance(g_vulkan_instance, NULL);
    xr_vk_bootstrap_reset();
}

unsigned xr_vk_bootstrap_physical_device_count()
{
    return g_physical_device_count;
}
'''


def patch_renderer_lifecycle(renderer: Path) -> None:
    source = renderer / "r2.cpp"
    text = source.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"

    init_log = '\t\tMsg("! [X-Ray Vulkan] Native Vulkan bootstrap unavailable; transitional renderer path remains active.");' + newline
    attach = (
        '\telse if (!xr_vk_bootstrap_attach_window(Device.m_hWnd, Device.dwWidth, Device.dwHeight))' + newline +
        '\t\tMsg("! [X-Ray Vulkan] Win32 surface/swapchain unavailable; transitional renderer path remains active.");' + newline
    )
    if "xr_vk_bootstrap_attach_window" not in text:
        if init_log not in text:
            raise RuntimeError("Vulkan runtime stack: lifecycle bootstrap log marker not found")
        text = text.replace(init_log, init_log + attach, 1)

    frame_pattern = r'(void\s+CRender::OnFrame\(\)\s*\r?\n\{\s*\r?\n)'
    if "xr_vk_bootstrap_frame();" not in text:
        frame_hook = (
            '\tif (xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent"))' + newline +
            '\t\txr_vk_bootstrap_frame();' + newline + newline
        )
        text, count = re.subn(frame_pattern, r'\1' + frame_hook, text, count=1)
        if count != 1:
            raise RuntimeError("Vulkan runtime stack: CRender::OnFrame hook not found")

    reset_pattern = r'(void\s+CRender::reset_end\(\)\s*\r?\n\{\s*\r?\n)'
    if "xr_vk_bootstrap_resize(Device.dwWidth" not in text:
        reset_hook = (
            '\tif (xr_vk_bootstrap_runtime_ready())' + newline +
            '\t\txr_vk_bootstrap_resize(Device.dwWidth, Device.dwHeight);' + newline + newline
        )
        text, count = re.subn(reset_pattern, r'\1' + reset_hook, text, count=1)
        if count != 1:
            raise RuntimeError("Vulkan runtime stack: CRender::reset_end hook not found")

    source.write_text(text, encoding="utf-8")


def install_runtime_stack(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    header = renderer / "vk_bootstrap.h"
    source = renderer / "vk_bootstrap.cpp"
    if not header.is_file() or not source.is_file():
        raise FileNotFoundError("Vulkan runtime stack requires generated bootstrap files")
    header.write_text(HEADER, encoding="utf-8")
    source.write_text(SOURCE, encoding="utf-8")
    patch_renderer_lifecycle(renderer)

    final = source.read_text(encoding="utf-8")
    required = (
        "vkCreateDevice", "VK_KHR_SWAPCHAIN_EXTENSION_NAME", "vkCreateWin32SurfaceKHR",
        "vkCreateSwapchainKHR", "vkAllocateCommandBuffers", "vkCreateSemaphore", "vkCreateFence",
        "vkAcquireNextImageKHR", "vkQueueSubmit", "vkQueuePresentKHR", "vkCmdClearColorImage",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan runtime stack validation failed: missing {token}")
    lifecycle = (renderer / "r2.cpp").read_text(encoding="utf-8", errors="ignore")
    for token in ("xr_vk_bootstrap_attach_window", "xr_vk_bootstrap_frame();", "xr_vk_bootstrap_resize"):
        if token not in lifecycle:
            raise RuntimeError(f"Vulkan runtime lifecycle validation failed: missing {token}")
    print("[vulkan-runtime] VkDevice + graphics/present queues + Win32 surface + swapchain + command/sync + clear/present path installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install native Vulkan runtime stack after the RC6 bootstrap/capability stages.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_runtime_stack(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
