from __future__ import annotations

import argparse
from pathlib import Path


def install_texture_bridge(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan texture bridge requires materialized descriptor state")

    text = source.read_text(encoding="utf-8")

    fn_marker = "    PFN_vkCmdBindDescriptorSets g_vkCmdBindDescriptorSets = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkCmdCopyBufferToImage g_vkCmdCopyBufferToImage = NULL;
'''
    if "g_vkCmdCopyBufferToImage" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan texture bridge: descriptor function marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkCmdBindDescriptorSets = NULL;\n"
    clear_block = clear_marker + '''        g_vkCmdCopyBufferToImage = NULL;
'''
    if "g_vkCmdCopyBufferToImage = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan texture bridge: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkCmdBindDescriptorSets);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCmdCopyBufferToImage);
'''
    if "XR_VK_LOAD_DEVICE(vkCmdCopyBufferToImage)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan texture bridge: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    struct xr_vk_texture_resource
    {
        VkImage image;
        VkDeviceMemory memory;
        VkImageView view;
        VkFormat format;
        u32 width;
        u32 height;
        u32 mip_levels;
        VkImageLayout layout;

        xr_vk_texture_resource()
            : image(VK_NULL_HANDLE), memory(VK_NULL_HANDLE), view(VK_NULL_HANDLE),
              format(VK_FORMAT_UNDEFINED), width(0), height(0), mip_levels(0),
              layout(VK_IMAGE_LAYOUT_UNDEFINED)
        {
        }
    };

    u32 xr_vk_max_mip_levels(u32 width, u32 height)
    {
        u32 extent = width > height ? width : height;
        u32 levels = 0;
        while (extent)
        {
            ++levels;
            extent >>= 1;
        }
        return levels;
    }

    void xr_vk_mip_extent(const xr_vk_texture_resource& texture, u32 mip_level, u32& width, u32& height)
    {
        width = texture.width;
        height = texture.height;
        for (u32 level = 0; level < mip_level; ++level)
        {
            if (width > 1)
                width >>= 1;
            if (height > 1)
                height >>= 1;
        }
    }

    VkFormat xr_vk_d3d_texture_format(D3DFORMAT format)
    {
        switch (format)
        {
        case D3DFMT_A8R8G8B8: return VK_FORMAT_B8G8R8A8_UNORM;
        case D3DFMT_X8R8G8B8: return VK_FORMAT_B8G8R8A8_UNORM;
        case D3DFMT_A8B8G8R8: return VK_FORMAT_R8G8B8A8_UNORM;
        case D3DFMT_X8B8G8R8: return VK_FORMAT_R8G8B8A8_UNORM;
        case D3DFMT_R5G6B5: return VK_FORMAT_R5G6B5_UNORM_PACK16;
        case D3DFMT_A1R5G5B5: return VK_FORMAT_A1R5G5B5_UNORM_PACK16;
        case D3DFMT_A4R4G4B4: return VK_FORMAT_B4G4R4A4_UNORM_PACK16;
        case D3DFMT_L8: return VK_FORMAT_R8_UNORM;
        case D3DFMT_A8L8: return VK_FORMAT_R8G8_UNORM;
        case D3DFMT_DXT1: return VK_FORMAT_BC1_RGBA_UNORM_BLOCK;
        case D3DFMT_DXT3: return VK_FORMAT_BC2_UNORM_BLOCK;
        case D3DFMT_DXT5: return VK_FORMAT_BC3_UNORM_BLOCK;
        default: return VK_FORMAT_UNDEFINED;
        }
    }

    bool xr_vk_texture_format_supported(VkFormat format)
    {
        if (format == VK_FORMAT_UNDEFINED || g_selected_physical_device == VK_NULL_HANDLE || !g_vkGetInstanceProcAddr)
            return false;
        PFN_vkGetPhysicalDeviceFormatProperties get_format_properties =
            reinterpret_cast<PFN_vkGetPhysicalDeviceFormatProperties>(
                g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceFormatProperties"));
        if (!get_format_properties)
            return false;
        VkFormatProperties properties = {};
        get_format_properties(g_selected_physical_device, format, &properties);
        return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT) != 0;
    }

    void xr_vk_destroy_texture(xr_vk_texture_resource& texture)
    {
        if (g_device != VK_NULL_HANDLE && texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
            g_vkDestroyImageView(g_device, texture.view, NULL);
        if (g_device != VK_NULL_HANDLE && texture.image != VK_NULL_HANDLE && g_vkDestroyImage)
            g_vkDestroyImage(g_device, texture.image, NULL);
        if (g_device != VK_NULL_HANDLE && texture.memory != VK_NULL_HANDLE && g_vkFreeMemory)
            g_vkFreeMemory(g_device, texture.memory, NULL);
        texture = xr_vk_texture_resource();
    }

    bool xr_vk_create_texture_2d(u32 width, u32 height, u32 mip_levels, D3DFORMAT d3d_format,
        xr_vk_texture_resource& texture)
    {
        if (!width || !height || !mip_levels || mip_levels > xr_vk_max_mip_levels(width, height) ||
            g_device == VK_NULL_HANDLE)
            return false;

        const VkFormat format = xr_vk_d3d_texture_format(d3d_format);
        if (!xr_vk_texture_format_supported(format))
            return false;

        xr_vk_destroy_texture(texture);
        VkImageCreateInfo image_info = {};
        image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        image_info.imageType = VK_IMAGE_TYPE_2D;
        image_info.format = format;
        image_info.extent.width = width;
        image_info.extent.height = height;
        image_info.extent.depth = 1;
        image_info.mipLevels = mip_levels;
        image_info.arrayLayers = 1;
        image_info.samples = VK_SAMPLE_COUNT_1_BIT;
        image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
        image_info.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
        image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        if (g_vkCreateImage(g_device, &image_info, NULL, &texture.image) != VK_SUCCESS)
            return false;

        VkMemoryRequirements requirements = {};
        g_vkGetImageMemoryRequirements(g_device, texture.image, &requirements);
        const unsigned memory_type = xr_vk_find_memory_type(requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        if (memory_type == ~0u)
        {
            xr_vk_destroy_texture(texture);
            return false;
        }

        VkMemoryAllocateInfo allocation = {};
        allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memory_type;
        if (g_vkAllocateMemory(g_device, &allocation, NULL, &texture.memory) != VK_SUCCESS ||
            g_vkBindImageMemory(g_device, texture.image, texture.memory, 0) != VK_SUCCESS)
        {
            xr_vk_destroy_texture(texture);
            return false;
        }

        VkImageViewCreateInfo view_info = {};
        view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        view_info.image = texture.image;
        view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
        view_info.format = format;
        view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        view_info.subresourceRange.baseMipLevel = 0;
        view_info.subresourceRange.levelCount = mip_levels;
        view_info.subresourceRange.baseArrayLayer = 0;
        view_info.subresourceRange.layerCount = 1;
        if (g_vkCreateImageView(g_device, &view_info, NULL, &texture.view) != VK_SUCCESS)
        {
            xr_vk_destroy_texture(texture);
            return false;
        }

        texture.format = format;
        texture.width = width;
        texture.height = height;
        texture.mip_levels = mip_levels;
        texture.layout = VK_IMAGE_LAYOUT_UNDEFINED;
        return true;
    }

    bool xr_vk_transition_texture(VkCommandBuffer command_buffer, xr_vk_texture_resource& texture,
        VkImageLayout new_layout)
    {
        if (command_buffer == VK_NULL_HANDLE || texture.image == VK_NULL_HANDLE || !g_vkCmdPipelineBarrier)
            return false;
        if (texture.layout == new_layout)
            return true;

        VkImageMemoryBarrier barrier = {};
        barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        barrier.oldLayout = texture.layout;
        barrier.newLayout = new_layout;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = texture.image;
        barrier.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        barrier.subresourceRange.levelCount = texture.mip_levels;
        barrier.subresourceRange.layerCount = 1;

        VkPipelineStageFlags src_stage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
        VkPipelineStageFlags dst_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
        if (texture.layout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL && new_layout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)
        {
            barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
            src_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
            dst_stage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
        }
        else if (texture.layout == VK_IMAGE_LAYOUT_UNDEFINED && new_layout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL)
        {
            barrier.srcAccessMask = 0;
            barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        }
        else
            return false;

        g_vkCmdPipelineBarrier(command_buffer, src_stage, dst_stage, 0, 0, NULL, 0, NULL, 1, &barrier);
        texture.layout = new_layout;
        return true;
    }

    bool xr_vk_copy_buffer_to_texture(VkCommandBuffer command_buffer, VkBuffer staging_buffer,
        VkDeviceSize staging_offset, xr_vk_texture_resource& texture, u32 mip_level,
        u32 width, u32 height)
    {
        if (command_buffer == VK_NULL_HANDLE || staging_buffer == VK_NULL_HANDLE ||
            texture.image == VK_NULL_HANDLE || mip_level >= texture.mip_levels || !width || !height ||
            !g_vkCmdCopyBufferToImage)
            return false;
        if (texture.layout != VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL)
            return false;

        u32 mip_width = 0;
        u32 mip_height = 0;
        xr_vk_mip_extent(texture, mip_level, mip_width, mip_height);
        if (width > mip_width || height > mip_height)
            return false;

        VkBufferImageCopy copy = {};
        copy.bufferOffset = staging_offset;
        copy.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        copy.imageSubresource.mipLevel = mip_level;
        copy.imageSubresource.baseArrayLayer = 0;
        copy.imageSubresource.layerCount = 1;
        copy.imageExtent.width = width;
        copy.imageExtent.height = height;
        copy.imageExtent.depth = 1;
        g_vkCmdCopyBufferToImage(command_buffer, staging_buffer, texture.image,
            VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
        return true;
    }

    bool xr_vk_allocate_texture_material(VkBuffer uniform_buffer, VkDeviceSize uniform_offset,
        VkDeviceSize uniform_range, const xr_vk_texture_resource& texture, VkDescriptorSet& descriptor_set)
    {
        if (texture.view == VK_NULL_HANDLE || texture.layout != VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL ||
            g_default_sampler == VK_NULL_HANDLE)
            return false;
        return xr_vk_allocate_material_descriptor(uniform_buffer, uniform_offset, uniform_range,
            texture.view, texture.layout, g_default_sampler, descriptor_set);
    }

'''
    if "xr_vk_create_texture_2d" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan texture bridge: shader-module helper marker not found")
        if "xr_vk_allocate_material_descriptor" not in text:
            raise RuntimeError("Vulkan texture bridge: material descriptor layer not materialized")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "PFN_vkCmdCopyBufferToImage",
        "XR_VK_LOAD_DEVICE(vkCmdCopyBufferToImage)",
        "struct xr_vk_texture_resource",
        "xr_vk_max_mip_levels",
        "xr_vk_mip_extent",
        "xr_vk_d3d_texture_format",
        "D3DFMT_A8R8G8B8", "VK_FORMAT_B8G8R8A8_UNORM",
        "D3DFMT_DXT1", "VK_FORMAT_BC1_RGBA_UNORM_BLOCK",
        "D3DFMT_DXT5", "VK_FORMAT_BC3_UNORM_BLOCK",
        "xr_vk_texture_format_supported",
        "VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT",
        "xr_vk_create_texture_2d",
        "mip_levels > xr_vk_max_mip_levels(width, height)",
        "VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT",
        "xr_vk_transition_texture",
        "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL",
        "VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL",
        "xr_vk_copy_buffer_to_texture",
        "xr_vk_mip_extent(texture, mip_level, mip_width, mip_height)",
        "width > mip_width || height > mip_height",
        "g_vkCmdCopyBufferToImage",
        "xr_vk_allocate_texture_material",
        "g_default_sampler",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan texture bridge validation failed: missing {token}")

    print("[vulkan-textures] D3D9 texture formats + bounded mip chain/extents + sampled image lifetime + upload transitions + material binding installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the transitional D3D9 texture to Vulkan sampled-image bridge.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_texture_bridge(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())