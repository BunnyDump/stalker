from __future__ import annotations

import argparse
from pathlib import Path

STATE_MARKER = "    VkFence g_frame_fence = VK_NULL_HANDLE;\n"
STATE_BLOCK = STATE_MARKER + r'''    VkFormat g_depth_format = VK_FORMAT_UNDEFINED;
    VkImage g_depth_image = VK_NULL_HANDLE;
    VkDeviceMemory g_depth_memory = VK_NULL_HANDLE;
    VkImageView g_depth_view = VK_NULL_HANDLE;
    VkRenderPass g_render_pass = VK_NULL_HANDLE;
    xr_vector<VkFramebuffer> g_framebuffers;
    VkDescriptorSetLayout g_descriptor_set_layout = VK_NULL_HANDLE;
    VkDescriptorPool g_descriptor_pool = VK_NULL_HANDLE;
    VkPipelineLayout g_pipeline_layout = VK_NULL_HANDLE;
    VkBuffer g_upload_buffer = VK_NULL_HANDLE;
    VkDeviceMemory g_upload_memory = VK_NULL_HANDLE;
    void* g_upload_mapped = NULL;
    const VkDeviceSize g_upload_capacity = 4ull * 1024ull * 1024ull;
'''

POINTER_MARKER = "    PFN_vkDeviceWaitIdle g_vkDeviceWaitIdle = NULL;\n"
POINTER_BLOCK = POINTER_MARKER + r'''    PFN_vkCreateImage g_vkCreateImage = NULL;
    PFN_vkDestroyImage g_vkDestroyImage = NULL;
    PFN_vkGetImageMemoryRequirements g_vkGetImageMemoryRequirements = NULL;
    PFN_vkAllocateMemory g_vkAllocateMemory = NULL;
    PFN_vkFreeMemory g_vkFreeMemory = NULL;
    PFN_vkBindImageMemory g_vkBindImageMemory = NULL;
    PFN_vkCreateRenderPass g_vkCreateRenderPass = NULL;
    PFN_vkDestroyRenderPass g_vkDestroyRenderPass = NULL;
    PFN_vkCreateFramebuffer g_vkCreateFramebuffer = NULL;
    PFN_vkDestroyFramebuffer g_vkDestroyFramebuffer = NULL;
    PFN_vkCmdBeginRenderPass g_vkCmdBeginRenderPass = NULL;
    PFN_vkCmdEndRenderPass g_vkCmdEndRenderPass = NULL;
    PFN_vkCreateDescriptorSetLayout g_vkCreateDescriptorSetLayout = NULL;
    PFN_vkDestroyDescriptorSetLayout g_vkDestroyDescriptorSetLayout = NULL;
    PFN_vkCreateDescriptorPool g_vkCreateDescriptorPool = NULL;
    PFN_vkDestroyDescriptorPool g_vkDestroyDescriptorPool = NULL;
    PFN_vkCreatePipelineLayout g_vkCreatePipelineLayout = NULL;
    PFN_vkDestroyPipelineLayout g_vkDestroyPipelineLayout = NULL;
    PFN_vkCreateBuffer g_vkCreateBuffer = NULL;
    PFN_vkDestroyBuffer g_vkDestroyBuffer = NULL;
    PFN_vkGetBufferMemoryRequirements g_vkGetBufferMemoryRequirements = NULL;
    PFN_vkBindBufferMemory g_vkBindBufferMemory = NULL;
    PFN_vkMapMemory g_vkMapMemory = NULL;
    PFN_vkUnmapMemory g_vkUnmapMemory = NULL;
'''

CLEAR_TABLE_MARKER = "        g_vkDeviceWaitIdle = NULL;\n"
CLEAR_TABLE_BLOCK = CLEAR_TABLE_MARKER + r'''        g_vkCreateImage = NULL;
        g_vkDestroyImage = NULL;
        g_vkGetImageMemoryRequirements = NULL;
        g_vkAllocateMemory = NULL;
        g_vkFreeMemory = NULL;
        g_vkBindImageMemory = NULL;
        g_vkCreateRenderPass = NULL;
        g_vkDestroyRenderPass = NULL;
        g_vkCreateFramebuffer = NULL;
        g_vkDestroyFramebuffer = NULL;
        g_vkCmdBeginRenderPass = NULL;
        g_vkCmdEndRenderPass = NULL;
        g_vkCreateDescriptorSetLayout = NULL;
        g_vkDestroyDescriptorSetLayout = NULL;
        g_vkCreateDescriptorPool = NULL;
        g_vkDestroyDescriptorPool = NULL;
        g_vkCreatePipelineLayout = NULL;
        g_vkDestroyPipelineLayout = NULL;
        g_vkCreateBuffer = NULL;
        g_vkDestroyBuffer = NULL;
        g_vkGetBufferMemoryRequirements = NULL;
        g_vkBindBufferMemory = NULL;
        g_vkMapMemory = NULL;
        g_vkUnmapMemory = NULL;
'''

LOAD_MARKER = "        XR_VK_LOAD_DEVICE(vkDeviceWaitIdle);\n"
LOAD_BLOCK = LOAD_MARKER + r'''        XR_VK_LOAD_DEVICE(vkCreateImage);
        XR_VK_LOAD_DEVICE(vkDestroyImage);
        XR_VK_LOAD_DEVICE(vkGetImageMemoryRequirements);
        XR_VK_LOAD_DEVICE(vkAllocateMemory);
        XR_VK_LOAD_DEVICE(vkFreeMemory);
        XR_VK_LOAD_DEVICE(vkBindImageMemory);
        XR_VK_LOAD_DEVICE(vkCreateRenderPass);
        XR_VK_LOAD_DEVICE(vkDestroyRenderPass);
        XR_VK_LOAD_DEVICE(vkCreateFramebuffer);
        XR_VK_LOAD_DEVICE(vkDestroyFramebuffer);
        XR_VK_LOAD_DEVICE(vkCmdBeginRenderPass);
        XR_VK_LOAD_DEVICE(vkCmdEndRenderPass);
        XR_VK_LOAD_DEVICE(vkCreateDescriptorSetLayout);
        XR_VK_LOAD_DEVICE(vkDestroyDescriptorSetLayout);
        XR_VK_LOAD_DEVICE(vkCreateDescriptorPool);
        XR_VK_LOAD_DEVICE(vkDestroyDescriptorPool);
        XR_VK_LOAD_DEVICE(vkCreatePipelineLayout);
        XR_VK_LOAD_DEVICE(vkDestroyPipelineLayout);
        XR_VK_LOAD_DEVICE(vkCreateBuffer);
        XR_VK_LOAD_DEVICE(vkDestroyBuffer);
        XR_VK_LOAD_DEVICE(vkGetBufferMemoryRequirements);
        XR_VK_LOAD_DEVICE(vkBindBufferMemory);
        XR_VK_LOAD_DEVICE(vkMapMemory);
        XR_VK_LOAD_DEVICE(vkUnmapMemory);
'''

HELPERS_MARKER = "    bool xr_vk_create_swapchain(unsigned width, unsigned height)\n"
HELPERS = r'''    bool xr_vk_find_memory_type(unsigned type_bits, VkMemoryPropertyFlags required, unsigned& memory_type)
    {
        PFN_vkGetPhysicalDeviceMemoryProperties get_memory_properties =
            reinterpret_cast<PFN_vkGetPhysicalDeviceMemoryProperties>(
                g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceMemoryProperties"));
        if (!get_memory_properties)
            return false;
        VkPhysicalDeviceMemoryProperties properties = {};
        get_memory_properties(g_selected_physical_device, &properties);
        for (unsigned i = 0; i < properties.memoryTypeCount; ++i)
        {
            if ((type_bits & (1u << i)) && (properties.memoryTypes[i].propertyFlags & required) == required)
            {
                memory_type = i;
                return true;
            }
        }
        return false;
    }

    bool xr_vk_choose_depth_format(VkFormat& format)
    {
        PFN_vkGetPhysicalDeviceFormatProperties get_format_properties =
            reinterpret_cast<PFN_vkGetPhysicalDeviceFormatProperties>(
                g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceFormatProperties"));
        if (!get_format_properties)
            return false;
        const VkFormat candidates[] = {VK_FORMAT_D32_SFLOAT, VK_FORMAT_D24_UNORM_S8_UINT, VK_FORMAT_D32_SFLOAT_S8_UINT};
        for (u32 i = 0; i < sizeof(candidates) / sizeof(candidates[0]); ++i)
        {
            VkFormatProperties properties = {};
            get_format_properties(g_selected_physical_device, candidates[i], &properties);
            if (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT)
            {
                format = candidates[i];
                return true;
            }
        }
        return false;
    }

    bool xr_vk_create_render_infrastructure()
    {
        if (!xr_vk_choose_depth_format(g_depth_format))
            return false;

        VkImageCreateInfo depth_info = {};
        depth_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        depth_info.imageType = VK_IMAGE_TYPE_2D;
        depth_info.format = g_depth_format;
        depth_info.extent.width = g_swapchain_extent.width;
        depth_info.extent.height = g_swapchain_extent.height;
        depth_info.extent.depth = 1;
        depth_info.mipLevels = 1;
        depth_info.arrayLayers = 1;
        depth_info.samples = VK_SAMPLE_COUNT_1_BIT;
        depth_info.tiling = VK_IMAGE_TILING_OPTIMAL;
        depth_info.usage = VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT;
        depth_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        depth_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        if (g_vkCreateImage(g_device, &depth_info, NULL, &g_depth_image) != VK_SUCCESS)
            return false;

        VkMemoryRequirements depth_requirements = {};
        g_vkGetImageMemoryRequirements(g_device, g_depth_image, &depth_requirements);
        unsigned depth_memory_type = 0;
        if (!xr_vk_find_memory_type(depth_requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, depth_memory_type))
            return false;
        VkMemoryAllocateInfo depth_allocate = {};
        depth_allocate.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        depth_allocate.allocationSize = depth_requirements.size;
        depth_allocate.memoryTypeIndex = depth_memory_type;
        if (g_vkAllocateMemory(g_device, &depth_allocate, NULL, &g_depth_memory) != VK_SUCCESS ||
            g_vkBindImageMemory(g_device, g_depth_image, g_depth_memory, 0) != VK_SUCCESS)
            return false;

        VkImageViewCreateInfo depth_view_info = {};
        depth_view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        depth_view_info.image = g_depth_image;
        depth_view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
        depth_view_info.format = g_depth_format;
        depth_view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
        if (g_depth_format == VK_FORMAT_D24_UNORM_S8_UINT || g_depth_format == VK_FORMAT_D32_SFLOAT_S8_UINT)
            depth_view_info.subresourceRange.aspectMask |= VK_IMAGE_ASPECT_STENCIL_BIT;
        depth_view_info.subresourceRange.levelCount = 1;
        depth_view_info.subresourceRange.layerCount = 1;
        if (g_vkCreateImageView(g_device, &depth_view_info, NULL, &g_depth_view) != VK_SUCCESS)
            return false;

        VkAttachmentDescription attachments[2] = {};
        attachments[0].format = g_swapchain_format;
        attachments[0].samples = VK_SAMPLE_COUNT_1_BIT;
        attachments[0].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachments[0].storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        attachments[0].stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachments[0].stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[0].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachments[0].finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        attachments[1].format = g_depth_format;
        attachments[1].samples = VK_SAMPLE_COUNT_1_BIT;
        attachments[1].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachments[1].storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[1].stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachments[1].stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[1].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachments[1].finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkAttachmentReference color_reference = {0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkAttachmentReference depth_reference = {1, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
        VkSubpassDescription subpass = {};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &color_reference;
        subpass.pDepthStencilAttachment = &depth_reference;

        VkSubpassDependency dependency = {};
        dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
        dependency.dstSubpass = 0;
        dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT | VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependency.dstStageMask = dependency.srcStageMask;
        dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT | VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;

        VkRenderPassCreateInfo render_pass_info = {};
        render_pass_info.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        render_pass_info.attachmentCount = 2;
        render_pass_info.pAttachments = attachments;
        render_pass_info.subpassCount = 1;
        render_pass_info.pSubpasses = &subpass;
        render_pass_info.dependencyCount = 1;
        render_pass_info.pDependencies = &dependency;
        if (g_vkCreateRenderPass(g_device, &render_pass_info, NULL, &g_render_pass) != VK_SUCCESS)
            return false;

        g_framebuffers.assign(g_swapchain_views.size(), VK_NULL_HANDLE);
        for (u32 i = 0; i < g_swapchain_views.size(); ++i)
        {
            VkImageView framebuffer_attachments[2] = {g_swapchain_views[i], g_depth_view};
            VkFramebufferCreateInfo framebuffer_info = {};
            framebuffer_info.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
            framebuffer_info.renderPass = g_render_pass;
            framebuffer_info.attachmentCount = 2;
            framebuffer_info.pAttachments = framebuffer_attachments;
            framebuffer_info.width = g_swapchain_extent.width;
            framebuffer_info.height = g_swapchain_extent.height;
            framebuffer_info.layers = 1;
            if (g_vkCreateFramebuffer(g_device, &framebuffer_info, NULL, &g_framebuffers[i]) != VK_SUCCESS)
                return false;
        }

        VkDescriptorSetLayoutBinding bindings[2] = {};
        bindings[0].binding = 0;
        bindings[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        bindings[0].descriptorCount = 1;
        bindings[0].stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
        bindings[1].binding = 1;
        bindings[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        bindings[1].descriptorCount = 1;
        bindings[1].stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT;
        VkDescriptorSetLayoutCreateInfo descriptor_layout_info = {};
        descriptor_layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        descriptor_layout_info.bindingCount = 2;
        descriptor_layout_info.pBindings = bindings;
        if (g_vkCreateDescriptorSetLayout(g_device, &descriptor_layout_info, NULL, &g_descriptor_set_layout) != VK_SUCCESS)
            return false;

        VkDescriptorPoolSize pool_sizes[3] = {};
        pool_sizes[0].type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER; pool_sizes[0].descriptorCount = 256;
        pool_sizes[1].type = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; pool_sizes[1].descriptorCount = 256;
        pool_sizes[2].type = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; pool_sizes[2].descriptorCount = 128;
        VkDescriptorPoolCreateInfo descriptor_pool_info = {};
        descriptor_pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        descriptor_pool_info.flags = VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT;
        descriptor_pool_info.maxSets = 256;
        descriptor_pool_info.poolSizeCount = 3;
        descriptor_pool_info.pPoolSizes = pool_sizes;
        if (g_vkCreateDescriptorPool(g_device, &descriptor_pool_info, NULL, &g_descriptor_pool) != VK_SUCCESS)
            return false;

        VkPipelineLayoutCreateInfo pipeline_layout_info = {};
        pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        pipeline_layout_info.setLayoutCount = 1;
        pipeline_layout_info.pSetLayouts = &g_descriptor_set_layout;
        if (g_vkCreatePipelineLayout(g_device, &pipeline_layout_info, NULL, &g_pipeline_layout) != VK_SUCCESS)
            return false;

        VkBufferCreateInfo upload_info = {};
        upload_info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        upload_info.size = g_upload_capacity;
        upload_info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT;
        upload_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        if (g_vkCreateBuffer(g_device, &upload_info, NULL, &g_upload_buffer) != VK_SUCCESS)
            return false;
        VkMemoryRequirements upload_requirements = {};
        g_vkGetBufferMemoryRequirements(g_device, g_upload_buffer, &upload_requirements);
        unsigned upload_memory_type = 0;
        if (!xr_vk_find_memory_type(upload_requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, upload_memory_type))
            return false;
        VkMemoryAllocateInfo upload_allocate = {};
        upload_allocate.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        upload_allocate.allocationSize = upload_requirements.size;
        upload_allocate.memoryTypeIndex = upload_memory_type;
        if (g_vkAllocateMemory(g_device, &upload_allocate, NULL, &g_upload_memory) != VK_SUCCESS ||
            g_vkBindBufferMemory(g_device, g_upload_buffer, g_upload_memory, 0) != VK_SUCCESS ||
            g_vkMapMemory(g_device, g_upload_memory, 0, g_upload_capacity, 0, &g_upload_mapped) != VK_SUCCESS)
            return false;

        return true;
    }

'''

CREATE_INFRA_MARKER = "        if (g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) != VK_SUCCESS)\n            return false;\n\n        return true;\n"
CREATE_INFRA_REPLACEMENT = "        if (g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) != VK_SUCCESS)\n            return false;\n\n        if (!xr_vk_create_render_infrastructure())\n            return false;\n\n        return true;\n"

DESTROY_FRAME_MARKER = "        if (g_device != VK_NULL_HANDLE && g_vkDestroyCommandPool && g_command_pool != VK_NULL_HANDLE)\n            g_vkDestroyCommandPool(g_device, g_command_pool, NULL);\n"
DESTROY_FRAME_PREFIX = r'''        if (g_device != VK_NULL_HANDLE && g_upload_mapped && g_vkUnmapMemory)
            g_vkUnmapMemory(g_device, g_upload_memory);
        g_upload_mapped = NULL;
        if (g_device != VK_NULL_HANDLE && g_vkDestroyBuffer && g_upload_buffer != VK_NULL_HANDLE)
            g_vkDestroyBuffer(g_device, g_upload_buffer, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkFreeMemory && g_upload_memory != VK_NULL_HANDLE)
            g_vkFreeMemory(g_device, g_upload_memory, NULL);
        g_upload_buffer = VK_NULL_HANDLE;
        g_upload_memory = VK_NULL_HANDLE;

        if (g_device != VK_NULL_HANDLE && g_vkDestroyPipelineLayout && g_pipeline_layout != VK_NULL_HANDLE)
            g_vkDestroyPipelineLayout(g_device, g_pipeline_layout, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroyDescriptorPool && g_descriptor_pool != VK_NULL_HANDLE)
            g_vkDestroyDescriptorPool(g_device, g_descriptor_pool, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroyDescriptorSetLayout && g_descriptor_set_layout != VK_NULL_HANDLE)
            g_vkDestroyDescriptorSetLayout(g_device, g_descriptor_set_layout, NULL);
        g_pipeline_layout = VK_NULL_HANDLE;
        g_descriptor_pool = VK_NULL_HANDLE;
        g_descriptor_set_layout = VK_NULL_HANDLE;

        if (g_device != VK_NULL_HANDLE && g_vkDestroyFramebuffer)
            for (u32 i = 0; i < g_framebuffers.size(); ++i)
                if (g_framebuffers[i] != VK_NULL_HANDLE) g_vkDestroyFramebuffer(g_device, g_framebuffers[i], NULL);
        g_framebuffers.clear();
        if (g_device != VK_NULL_HANDLE && g_vkDestroyRenderPass && g_render_pass != VK_NULL_HANDLE)
            g_vkDestroyRenderPass(g_device, g_render_pass, NULL);
        g_render_pass = VK_NULL_HANDLE;
        if (g_device != VK_NULL_HANDLE && g_vkDestroyImageView && g_depth_view != VK_NULL_HANDLE)
            g_vkDestroyImageView(g_device, g_depth_view, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkDestroyImage && g_depth_image != VK_NULL_HANDLE)
            g_vkDestroyImage(g_device, g_depth_image, NULL);
        if (g_device != VK_NULL_HANDLE && g_vkFreeMemory && g_depth_memory != VK_NULL_HANDLE)
            g_vkFreeMemory(g_device, g_depth_memory, NULL);
        g_depth_view = VK_NULL_HANDLE;
        g_depth_image = VK_NULL_HANDLE;
        g_depth_memory = VK_NULL_HANDLE;
        g_depth_format = VK_FORMAT_UNDEFINED;

'''

FRAME_OLD_START = "    VkImageMemoryBarrier to_transfer = {};\n"
FRAME_OLD_END = "    g_vkCmdPipelineBarrier(g_command_buffers[image_index], VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,\n        0, 0, NULL, 0, NULL, 1, &to_present);\n"
FRAME_RENDERPASS = r'''    VkClearValue clear_values[2] = {};
    clear_values[0].color.float32[0] = 0.015f;
    clear_values[0].color.float32[1] = 0.025f;
    clear_values[0].color.float32[2] = 0.040f;
    clear_values[0].color.float32[3] = 1.0f;
    clear_values[1].depthStencil.depth = 1.0f;
    clear_values[1].depthStencil.stencil = 0;

    VkRenderPassBeginInfo render_pass_begin = {};
    render_pass_begin.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    render_pass_begin.renderPass = g_render_pass;
    render_pass_begin.framebuffer = g_framebuffers[image_index];
    render_pass_begin.renderArea.extent = g_swapchain_extent;
    render_pass_begin.clearValueCount = 2;
    render_pass_begin.pClearValues = clear_values;
    g_vkCmdBeginRenderPass(g_command_buffers[image_index], &render_pass_begin, VK_SUBPASS_CONTENTS_INLINE);
    g_vkCmdEndRenderPass(g_command_buffers[image_index]);
'''


def patch_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old, new, 1)


def enable_render_infrastructure(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    text = patch_once(text, STATE_MARKER, STATE_BLOCK, "render infra state")
    text = patch_once(text, POINTER_MARKER, POINTER_BLOCK, "render infra function pointers")
    text = patch_once(text, CLEAR_TABLE_MARKER, CLEAR_TABLE_BLOCK, "render infra function-table reset")
    text = patch_once(text, LOAD_MARKER, LOAD_BLOCK, "render infra function loading")
    text = patch_once(text, HELPERS_MARKER, HELPERS + HELPERS_MARKER, "render infra helpers")
    text = patch_once(text, CREATE_INFRA_MARKER, CREATE_INFRA_REPLACEMENT, "render infra creation")
    text = patch_once(text, DESTROY_FRAME_MARKER, DESTROY_FRAME_PREFIX + DESTROY_FRAME_MARKER, "render infra destruction")

    start = text.find(FRAME_OLD_START)
    end = text.find(FRAME_OLD_END, start)
    if start < 0 or end < 0:
        raise RuntimeError("render infra frame clear block not found")
    end += len(FRAME_OLD_END)
    text = text[:start] + FRAME_RENDERPASS + text[end:]
    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT", "vkCreateRenderPass", "vkCreateFramebuffer",
        "vkCmdBeginRenderPass", "vkCreateDescriptorSetLayout", "vkCreateDescriptorPool",
        "vkCreatePipelineLayout", "vkCreateBuffer", "vkMapMemory", "g_upload_capacity",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan render infrastructure validation failed: missing {token}")
    print("[vulkan-render-infra] depth target + render pass/framebuffers + descriptor/pipeline layout + mapped upload buffer installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add Vulkan render-target, descriptor and upload infrastructure to the RC6 runtime stack.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable_render_infrastructure(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
