from __future__ import annotations

import argparse
from pathlib import Path


def install_render_core(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan render core requires materialized runtime stack")

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkFence g_frame_fence = VK_NULL_HANDLE;\n"
    state_block = state_marker + '''    VkImage g_depth_image = VK_NULL_HANDLE;
    VkDeviceMemory g_depth_memory = VK_NULL_HANDLE;
    VkImageView g_depth_view = VK_NULL_HANDLE;
    VkFormat g_depth_format = VK_FORMAT_UNDEFINED;
    VkRenderPass g_render_pass = VK_NULL_HANDLE;
    VkPipelineLayout g_pipeline_layout = VK_NULL_HANDLE;
    VkDescriptorSetLayout g_descriptor_set_layout = VK_NULL_HANDLE;
    VkDescriptorPool g_descriptor_pool = VK_NULL_HANDLE;
    VkSampler g_default_sampler = VK_NULL_HANDLE;
    VkBuffer g_uniform_buffer = VK_NULL_HANDLE;
    VkDeviceMemory g_uniform_memory = VK_NULL_HANDLE;
    VkBuffer g_upload_buffer = VK_NULL_HANDLE;
    VkDeviceMemory g_upload_memory = VK_NULL_HANDLE;
    xr_vector<VkFramebuffer> g_framebuffers;
'''
    if "g_depth_image" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan render core: state marker not found")
        text = text.replace(state_marker, state_block, 1)

    fn_marker = "    PFN_vkDeviceWaitIdle g_vkDeviceWaitIdle = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkGetPhysicalDeviceMemoryProperties g_vkGetPhysicalDeviceMemoryProperties = NULL;
    PFN_vkCreateImage g_vkCreateImage = NULL;
    PFN_vkDestroyImage g_vkDestroyImage = NULL;
    PFN_vkGetImageMemoryRequirements g_vkGetImageMemoryRequirements = NULL;
    PFN_vkAllocateMemory g_vkAllocateMemory = NULL;
    PFN_vkFreeMemory g_vkFreeMemory = NULL;
    PFN_vkBindImageMemory g_vkBindImageMemory = NULL;
    PFN_vkCreateRenderPass g_vkCreateRenderPass = NULL;
    PFN_vkDestroyRenderPass g_vkDestroyRenderPass = NULL;
    PFN_vkCreateFramebuffer g_vkCreateFramebuffer = NULL;
    PFN_vkDestroyFramebuffer g_vkDestroyFramebuffer = NULL;
    PFN_vkCreatePipelineLayout g_vkCreatePipelineLayout = NULL;
    PFN_vkDestroyPipelineLayout g_vkDestroyPipelineLayout = NULL;
    PFN_vkCreateDescriptorSetLayout g_vkCreateDescriptorSetLayout = NULL;
    PFN_vkDestroyDescriptorSetLayout g_vkDestroyDescriptorSetLayout = NULL;
    PFN_vkCreateDescriptorPool g_vkCreateDescriptorPool = NULL;
    PFN_vkDestroyDescriptorPool g_vkDestroyDescriptorPool = NULL;
    PFN_vkCreateSampler g_vkCreateSampler = NULL;
    PFN_vkDestroySampler g_vkDestroySampler = NULL;
    PFN_vkCreateBuffer g_vkCreateBuffer = NULL;
    PFN_vkDestroyBuffer g_vkDestroyBuffer = NULL;
    PFN_vkGetBufferMemoryRequirements g_vkGetBufferMemoryRequirements = NULL;
    PFN_vkBindBufferMemory g_vkBindBufferMemory = NULL;
    PFN_vkMapMemory g_vkMapMemory = NULL;
    PFN_vkUnmapMemory g_vkUnmapMemory = NULL;
'''
    if "g_vkCreateRenderPass" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan render core: function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkDeviceWaitIdle = NULL;\n"
    clear_block = clear_marker + '''        g_vkGetPhysicalDeviceMemoryProperties = NULL;
        g_vkCreateImage = NULL;
        g_vkDestroyImage = NULL;
        g_vkGetImageMemoryRequirements = NULL;
        g_vkAllocateMemory = NULL;
        g_vkFreeMemory = NULL;
        g_vkBindImageMemory = NULL;
        g_vkCreateRenderPass = NULL;
        g_vkDestroyRenderPass = NULL;
        g_vkCreateFramebuffer = NULL;
        g_vkDestroyFramebuffer = NULL;
        g_vkCreatePipelineLayout = NULL;
        g_vkDestroyPipelineLayout = NULL;
        g_vkCreateDescriptorSetLayout = NULL;
        g_vkDestroyDescriptorSetLayout = NULL;
        g_vkCreateDescriptorPool = NULL;
        g_vkDestroyDescriptorPool = NULL;
        g_vkCreateSampler = NULL;
        g_vkDestroySampler = NULL;
        g_vkCreateBuffer = NULL;
        g_vkDestroyBuffer = NULL;
        g_vkGetBufferMemoryRequirements = NULL;
        g_vkBindBufferMemory = NULL;
        g_vkMapMemory = NULL;
        g_vkUnmapMemory = NULL;
'''
    if "g_vkCreateRenderPass = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan render core: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkDeviceWaitIdle);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCreateImage);
        XR_VK_LOAD_DEVICE(vkDestroyImage);
        XR_VK_LOAD_DEVICE(vkGetImageMemoryRequirements);
        XR_VK_LOAD_DEVICE(vkAllocateMemory);
        XR_VK_LOAD_DEVICE(vkFreeMemory);
        XR_VK_LOAD_DEVICE(vkBindImageMemory);
        XR_VK_LOAD_DEVICE(vkCreateRenderPass);
        XR_VK_LOAD_DEVICE(vkDestroyRenderPass);
        XR_VK_LOAD_DEVICE(vkCreateFramebuffer);
        XR_VK_LOAD_DEVICE(vkDestroyFramebuffer);
        XR_VK_LOAD_DEVICE(vkCreatePipelineLayout);
        XR_VK_LOAD_DEVICE(vkDestroyPipelineLayout);
        XR_VK_LOAD_DEVICE(vkCreateDescriptorSetLayout);
        XR_VK_LOAD_DEVICE(vkDestroyDescriptorSetLayout);
        XR_VK_LOAD_DEVICE(vkCreateDescriptorPool);
        XR_VK_LOAD_DEVICE(vkDestroyDescriptorPool);
        XR_VK_LOAD_DEVICE(vkCreateSampler);
        XR_VK_LOAD_DEVICE(vkDestroySampler);
        XR_VK_LOAD_DEVICE(vkCreateBuffer);
        XR_VK_LOAD_DEVICE(vkDestroyBuffer);
        XR_VK_LOAD_DEVICE(vkGetBufferMemoryRequirements);
        XR_VK_LOAD_DEVICE(vkBindBufferMemory);
        XR_VK_LOAD_DEVICE(vkMapMemory);
        XR_VK_LOAD_DEVICE(vkUnmapMemory);
'''
    if "XR_VK_LOAD_DEVICE(vkCreateRenderPass)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan render core: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    helper_marker = "    bool xr_vk_create_swapchain(unsigned width, unsigned height)\n    {\n"
    helpers = r'''    unsigned xr_vk_find_memory_type(unsigned type_bits, VkMemoryPropertyFlags required)
    {
        VkPhysicalDeviceMemoryProperties props = {};
        g_vkGetPhysicalDeviceMemoryProperties(g_selected_physical_device, &props);
        for (unsigned i = 0; i < props.memoryTypeCount; ++i)
            if ((type_bits & (1u << i)) && (props.memoryTypes[i].propertyFlags & required) == required)
                return i;
        return ~0u;
    }

    bool xr_vk_create_buffer(VkDeviceSize size, VkBufferUsageFlags usage, VkMemoryPropertyFlags memory_flags,
        VkBuffer& buffer, VkDeviceMemory& memory)
    {
        VkBufferCreateInfo info = {};
        info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        info.size = size;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        if (g_vkCreateBuffer(g_device, &info, NULL, &buffer) != VK_SUCCESS)
            return false;
        VkMemoryRequirements requirements = {};
        g_vkGetBufferMemoryRequirements(g_device, buffer, &requirements);
        const unsigned memory_type = xr_vk_find_memory_type(requirements.memoryTypeBits, memory_flags);
        if (memory_type == ~0u)
            return false;
        VkMemoryAllocateInfo allocation = {};
        allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memory_type;
        if (g_vkAllocateMemory(g_device, &allocation, NULL, &memory) != VK_SUCCESS)
            return false;
        return g_vkBindBufferMemory(g_device, buffer, memory, 0) == VK_SUCCESS;
    }

    bool xr_vk_create_render_core()
    {
        PFN_vkGetPhysicalDeviceFormatProperties get_format_properties =
            reinterpret_cast<PFN_vkGetPhysicalDeviceFormatProperties>(
                g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceFormatProperties"));
        g_vkGetPhysicalDeviceMemoryProperties = reinterpret_cast<PFN_vkGetPhysicalDeviceMemoryProperties>(
            g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceMemoryProperties"));
        if (!get_format_properties || !g_vkGetPhysicalDeviceMemoryProperties)
            return false;

        const VkFormat depth_candidates[] = {VK_FORMAT_D32_SFLOAT, VK_FORMAT_D24_UNORM_S8_UINT, VK_FORMAT_D16_UNORM};
        for (u32 i = 0; i < sizeof(depth_candidates) / sizeof(depth_candidates[0]); ++i)
        {
            VkFormatProperties properties = {};
            get_format_properties(g_selected_physical_device, depth_candidates[i], &properties);
            if (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT)
            {
                g_depth_format = depth_candidates[i];
                break;
            }
        }
        if (g_depth_format == VK_FORMAT_UNDEFINED)
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
        const unsigned depth_memory_type = xr_vk_find_memory_type(depth_requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        if (depth_memory_type == ~0u)
            return false;
        VkMemoryAllocateInfo depth_allocation = {};
        depth_allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        depth_allocation.allocationSize = depth_requirements.size;
        depth_allocation.memoryTypeIndex = depth_memory_type;
        if (g_vkAllocateMemory(g_device, &depth_allocation, NULL, &g_depth_memory) != VK_SUCCESS ||
            g_vkBindImageMemory(g_device, g_depth_image, g_depth_memory, 0) != VK_SUCCESS)
            return false;

        VkImageViewCreateInfo depth_view = {};
        depth_view.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        depth_view.image = g_depth_image;
        depth_view.viewType = VK_IMAGE_VIEW_TYPE_2D;
        depth_view.format = g_depth_format;
        depth_view.subresourceRange.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
        if (g_depth_format == VK_FORMAT_D24_UNORM_S8_UINT)
            depth_view.subresourceRange.aspectMask |= VK_IMAGE_ASPECT_STENCIL_BIT;
        depth_view.subresourceRange.levelCount = 1;
        depth_view.subresourceRange.layerCount = 1;
        if (g_vkCreateImageView(g_device, &depth_view, NULL, &g_depth_view) != VK_SUCCESS)
            return false;

        VkAttachmentDescription attachments[2] = {};
        attachments[0].format = g_swapchain_format;
        attachments[0].samples = VK_SAMPLE_COUNT_1_BIT;
        attachments[0].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachments[0].storeOp = VK_ATTACHMENT_STORE_OP_STORE;
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
            VkImageView views[2] = {g_swapchain_views[i], g_depth_view};
            VkFramebufferCreateInfo fb = {};
            fb.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
            fb.renderPass = g_render_pass;
            fb.attachmentCount = 2;
            fb.pAttachments = views;
            fb.width = g_swapchain_extent.width;
            fb.height = g_swapchain_extent.height;
            fb.layers = 1;
            if (g_vkCreateFramebuffer(g_device, &fb, NULL, &g_framebuffers[i]) != VK_SUCCESS)
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
        VkDescriptorSetLayoutCreateInfo descriptor_layout = {};
        descriptor_layout.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        descriptor_layout.bindingCount = 2;
        descriptor_layout.pBindings = bindings;
        if (g_vkCreateDescriptorSetLayout(g_device, &descriptor_layout, NULL, &g_descriptor_set_layout) != VK_SUCCESS)
            return false;

        VkPipelineLayoutCreateInfo pipeline_layout = {};
        pipeline_layout.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        pipeline_layout.setLayoutCount = 1;
        pipeline_layout.pSetLayouts = &g_descriptor_set_layout;
        if (g_vkCreatePipelineLayout(g_device, &pipeline_layout, NULL, &g_pipeline_layout) != VK_SUCCESS)
            return false;

        VkDescriptorPoolSize pool_sizes[2] = {};
        pool_sizes[0].type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        pool_sizes[0].descriptorCount = 256;
        pool_sizes[1].type = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        pool_sizes[1].descriptorCount = 256;
        VkDescriptorPoolCreateInfo pool = {};
        pool.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        pool.flags = VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT;
        pool.maxSets = 256;
        pool.poolSizeCount = 2;
        pool.pPoolSizes = pool_sizes;
        if (g_vkCreateDescriptorPool(g_device, &pool, NULL, &g_descriptor_pool) != VK_SUCCESS)
            return false;

        VkSamplerCreateInfo sampler = {};
        sampler.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
        sampler.magFilter = VK_FILTER_LINEAR;
        sampler.minFilter = VK_FILTER_LINEAR;
        sampler.mipmapMode = VK_SAMPLER_MIPMAP_MODE_LINEAR;
        sampler.addressModeU = VK_SAMPLER_ADDRESS_MODE_REPEAT;
        sampler.addressModeV = VK_SAMPLER_ADDRESS_MODE_REPEAT;
        sampler.addressModeW = VK_SAMPLER_ADDRESS_MODE_REPEAT;
        sampler.maxLod = VK_LOD_CLAMP_NONE;
        if (g_vkCreateSampler(g_device, &sampler, NULL, &g_default_sampler) != VK_SUCCESS)
            return false;

        if (!xr_vk_create_buffer(64 * 1024, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_uniform_buffer, g_uniform_memory))
            return false;
        if (!xr_vk_create_buffer(4 * 1024 * 1024,
                VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_upload_buffer, g_upload_memory))
            return false;
        return true;
    }

'''
    if "xr_vk_create_render_core()" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan render core: swapchain helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    create_marker = "        if (g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) != VK_SUCCESS)\n            return false;\n\n        return true;\n"
    create_replacement = "        if (g_vkCreateFence(g_device, &fence_info, NULL, &g_frame_fence) != VK_SUCCESS)\n            return false;\n\n        return xr_vk_create_render_core();\n"
    if "return xr_vk_create_render_core();" not in text:
        if create_marker not in text:
            raise RuntimeError("Vulkan render core: frame-resource completion marker not found")
        text = text.replace(create_marker, create_replacement, 1)

    # Insert conservative cleanup before swapchain views/images are destroyed.
    cleanup_marker = "        if (g_device != VK_NULL_HANDLE && g_vkDestroyCommandPool && g_command_pool != VK_NULL_HANDLE)\n"
    cleanup = r'''        if (g_device != VK_NULL_HANDLE)
        {
            for (u32 i = 0; i < g_framebuffers.size(); ++i)
                if (g_framebuffers[i] != VK_NULL_HANDLE && g_vkDestroyFramebuffer)
                    g_vkDestroyFramebuffer(g_device, g_framebuffers[i], NULL);
            g_framebuffers.clear();
            if (g_default_sampler != VK_NULL_HANDLE && g_vkDestroySampler) g_vkDestroySampler(g_device, g_default_sampler, NULL);
            if (g_descriptor_pool != VK_NULL_HANDLE && g_vkDestroyDescriptorPool) g_vkDestroyDescriptorPool(g_device, g_descriptor_pool, NULL);
            if (g_pipeline_layout != VK_NULL_HANDLE && g_vkDestroyPipelineLayout) g_vkDestroyPipelineLayout(g_device, g_pipeline_layout, NULL);
            if (g_descriptor_set_layout != VK_NULL_HANDLE && g_vkDestroyDescriptorSetLayout) g_vkDestroyDescriptorSetLayout(g_device, g_descriptor_set_layout, NULL);
            if (g_render_pass != VK_NULL_HANDLE && g_vkDestroyRenderPass) g_vkDestroyRenderPass(g_device, g_render_pass, NULL);
            if (g_depth_view != VK_NULL_HANDLE && g_vkDestroyImageView) g_vkDestroyImageView(g_device, g_depth_view, NULL);
            if (g_depth_image != VK_NULL_HANDLE && g_vkDestroyImage) g_vkDestroyImage(g_device, g_depth_image, NULL);
            if (g_depth_memory != VK_NULL_HANDLE && g_vkFreeMemory) g_vkFreeMemory(g_device, g_depth_memory, NULL);
            if (g_uniform_buffer != VK_NULL_HANDLE && g_vkDestroyBuffer) g_vkDestroyBuffer(g_device, g_uniform_buffer, NULL);
            if (g_uniform_memory != VK_NULL_HANDLE && g_vkFreeMemory) g_vkFreeMemory(g_device, g_uniform_memory, NULL);
            if (g_upload_buffer != VK_NULL_HANDLE && g_vkDestroyBuffer) g_vkDestroyBuffer(g_device, g_upload_buffer, NULL);
            if (g_upload_memory != VK_NULL_HANDLE && g_vkFreeMemory) g_vkFreeMemory(g_device, g_upload_memory, NULL);
        }
        g_default_sampler = VK_NULL_HANDLE;
        g_descriptor_pool = VK_NULL_HANDLE;
        g_pipeline_layout = VK_NULL_HANDLE;
        g_descriptor_set_layout = VK_NULL_HANDLE;
        g_render_pass = VK_NULL_HANDLE;
        g_depth_view = VK_NULL_HANDLE;
        g_depth_image = VK_NULL_HANDLE;
        g_depth_memory = VK_NULL_HANDLE;
        g_depth_format = VK_FORMAT_UNDEFINED;
        g_uniform_buffer = VK_NULL_HANDLE;
        g_uniform_memory = VK_NULL_HANDLE;
        g_upload_buffer = VK_NULL_HANDLE;
        g_upload_memory = VK_NULL_HANDLE;

'''
    if "g_depth_memory = VK_NULL_HANDLE;" not in text[text.find("void xr_vk_destroy_frame_resources"):text.find("void xr_vk_destroy_frame_resources") + 7000]:
        if cleanup_marker not in text:
            raise RuntimeError("Vulkan render core: cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup + cleanup_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT", "vkCreateRenderPass", "vkCreateFramebuffer",
        "vkCreateDescriptorSetLayout", "vkCreateDescriptorPool", "vkCreateSampler", "vkCreateBuffer",
        "VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER", "VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan render core validation failed: missing {token}")
    print("[vulkan-render-core] depth attachment + render pass/framebuffers + descriptor/pipeline layout + uniform/upload buffers installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Vulkan render-core infrastructure for RC6 xrRender_VK.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_render_core(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
