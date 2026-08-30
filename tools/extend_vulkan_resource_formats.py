from __future__ import annotations

import argparse
from pathlib import Path

HEADER_ENUM = r'''enum XrVkTextureFormat
{
    XR_VK_TEXTURE_RGBA8_UNORM = 0,
    XR_VK_TEXTURE_RGBA8_SNORM = 1,
    XR_VK_TEXTURE_RG8_UNORM = 2
};

unsigned xr_vk_texture_create(const void* pixels, unsigned width, unsigned height, unsigned depth, XrVkTextureFormat format);
'''

GENERIC_IMPL = r'''namespace
{
    bool xr_vk_resolve_texture_format(XrVkTextureFormat format, VkFormat& vk_format, unsigned& bytes_per_pixel)
    {
        switch (format)
        {
        case XR_VK_TEXTURE_RGBA8_UNORM:
            vk_format = VK_FORMAT_R8G8B8A8_UNORM;
            bytes_per_pixel = 4;
            return true;
        case XR_VK_TEXTURE_RGBA8_SNORM:
            vk_format = VK_FORMAT_R8G8B8A8_SNORM;
            bytes_per_pixel = 4;
            return true;
        case XR_VK_TEXTURE_RG8_UNORM:
            vk_format = VK_FORMAT_R8G8_UNORM;
            bytes_per_pixel = 2;
            return true;
        default:
            vk_format = VK_FORMAT_UNDEFINED;
            bytes_per_pixel = 0;
            return false;
        }
    }

    bool xr_vk_texture_format_supported(VkFormat format)
    {
        if (g_vulkan_instance == VK_NULL_HANDLE || g_selected_physical_device == VK_NULL_HANDLE || !g_vkGetInstanceProcAddr)
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
}

unsigned xr_vk_texture_create(const void* pixels, unsigned width, unsigned height, unsigned depth, XrVkTextureFormat format)
{
    if (!pixels || !width || !height || !depth || g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE)
        return 0;

    VkFormat vk_format = VK_FORMAT_UNDEFINED;
    unsigned bytes_per_pixel = 0;
    if (!xr_vk_resolve_texture_format(format, vk_format, bytes_per_pixel) || !xr_vk_texture_format_supported(vk_format))
        return 0;

    const u64 byte_count = u64(width) * u64(height) * u64(depth) * u64(bytes_per_pixel);
    if (!byte_count || byte_count > 4ull * 1024ull * 1024ull)
        return 0;

    void* mapped = NULL;
    if (g_vkMapMemory(g_device, g_upload_memory, 0, VkDeviceSize(byte_count), 0, &mapped) != VK_SUCCESS || !mapped)
        return 0;
    Memory.mem_copy(mapped, pixels, size_t(byte_count));
    g_vkUnmapMemory(g_device, g_upload_memory);

    XrVkTexture texture;
    texture.width = width;
    texture.height = height;
    texture.depth = depth;

    VkImageCreateInfo image_info = {};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.imageType = depth > 1 ? VK_IMAGE_TYPE_3D : VK_IMAGE_TYPE_2D;
    image_info.format = vk_format;
    image_info.extent.width = width;
    image_info.extent.height = height;
    image_info.extent.depth = depth;
    image_info.mipLevels = 1;
    image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
    image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    if (g_vkCreateImage(g_device, &image_info, NULL, &texture.image) != VK_SUCCESS)
        return 0;

    VkMemoryRequirements req = {};
    g_vkGetImageMemoryRequirements(g_device, texture.image, &req);
    const unsigned memory_type = xr_vk_find_memory_type(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    if (memory_type == ~0u)
    {
        xr_vk_destroy_texture_object(texture);
        return 0;
    }

    VkMemoryAllocateInfo allocation = {};
    allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    allocation.allocationSize = req.size;
    allocation.memoryTypeIndex = memory_type;
    if (g_vkAllocateMemory(g_device, &allocation, NULL, &texture.memory) != VK_SUCCESS ||
        g_vkBindImageMemory(g_device, texture.image, texture.memory, 0) != VK_SUCCESS)
    {
        xr_vk_destroy_texture_object(texture);
        return 0;
    }

    VkImageViewCreateInfo view_info = {};
    view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    view_info.image = texture.image;
    view_info.viewType = depth > 1 ? VK_IMAGE_VIEW_TYPE_3D : VK_IMAGE_VIEW_TYPE_2D;
    view_info.format = vk_format;
    view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    view_info.subresourceRange.levelCount = 1;
    view_info.subresourceRange.layerCount = 1;
    if (g_vkCreateImageView(g_device, &view_info, NULL, &texture.view) != VK_SUCCESS ||
        !xr_vk_submit_texture_upload(texture.image, width, height, depth))
    {
        xr_vk_destroy_texture_object(texture);
        return 0;
    }

    VkDescriptorSetAllocateInfo set_alloc = {};
    set_alloc.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    set_alloc.descriptorPool = g_descriptor_pool;
    set_alloc.descriptorSetCount = 1;
    set_alloc.pSetLayouts = &g_descriptor_set_layout;
    if (g_vkAllocateDescriptorSets(g_device, &set_alloc, &texture.descriptor_set) != VK_SUCCESS)
    {
        xr_vk_destroy_texture_object(texture);
        return 0;
    }

    VkDescriptorBufferInfo uniform = {g_uniform_buffer, 0, 64 * 1024};
    VkDescriptorImageInfo image = {g_default_sampler, texture.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkWriteDescriptorSet writes[2] = {};
    writes[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    writes[0].dstSet = texture.descriptor_set;
    writes[0].dstBinding = 0;
    writes[0].descriptorCount = 1;
    writes[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    writes[0].pBufferInfo = &uniform;
    writes[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    writes[1].dstSet = texture.descriptor_set;
    writes[1].dstBinding = 1;
    writes[1].descriptorCount = 1;
    writes[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    writes[1].pImageInfo = &image;
    g_vkUpdateDescriptorSets(g_device, 2, writes, 0, NULL);

    for (u32 i = 0; i < g_textures.size(); ++i)
    {
        if (g_textures[i].image == VK_NULL_HANDLE)
        {
            g_textures[i] = texture;
            return i + 1;
        }
    }
    g_textures.push_back(texture);
    return g_textures.size();
}

'''


def extend(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan resource-format extension requires materialized resource upload layer")

    header_text = header.read_text(encoding="utf-8")
    if "enum XrVkTextureFormat" not in header_text:
        marker = "unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height);\n"
        if marker not in header_text:
            raise RuntimeError("resource-format header marker not found")
        header_text = header_text.replace(marker, HEADER_ENUM + marker, 1)
        header.write_text(header_text, encoding="utf-8")

    text = source.read_text(encoding="utf-8")

    old_struct = (
        "        unsigned width;\n"
        "        unsigned height;\n"
        "        XrVkTexture() : image(VK_NULL_HANDLE), memory(VK_NULL_HANDLE), view(VK_NULL_HANDLE),\n"
        "            descriptor_set(VK_NULL_HANDLE), width(0), height(0) {}\n"
    )
    new_struct = (
        "        unsigned width;\n"
        "        unsigned height;\n"
        "        unsigned depth;\n"
        "        XrVkTexture() : image(VK_NULL_HANDLE), memory(VK_NULL_HANDLE), view(VK_NULL_HANDLE),\n"
        "            descriptor_set(VK_NULL_HANDLE), width(0), height(0), depth(0) {}\n"
    )
    if "unsigned depth;" not in text:
        if old_struct not in text:
            raise RuntimeError("resource-format texture-state marker not found")
        text = text.replace(old_struct, new_struct, 1)

    old_upload = "    bool xr_vk_submit_texture_upload(VkImage image, unsigned width, unsigned height)\n"
    new_upload = "    bool xr_vk_submit_texture_upload(VkImage image, unsigned width, unsigned height, unsigned depth)\n"
    if old_upload in text:
        text = text.replace(old_upload, new_upload, 1)
    elif new_upload not in text:
        raise RuntimeError("resource-format upload helper marker not found")

    if "copy.imageExtent.depth = depth;" not in text:
        if "copy.imageExtent.depth = 1;" not in text:
            raise RuntimeError("resource-format copy depth marker not found")
        text = text.replace("copy.imageExtent.depth = 1;", "copy.imageExtent.depth = depth;", 1)

    text = text.replace(
        "!xr_vk_submit_texture_upload(texture.image, width, height))",
        "!xr_vk_submit_texture_upload(texture.image, width, height, 1))",
        1,
    )

    if "unsigned xr_vk_texture_create(const void* pixels" not in text:
        marker = "unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height)\n"
        if marker not in text:
            raise RuntimeError("resource-format public implementation marker not found")
        text = text.replace(marker, GENERIC_IMPL + marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    header_final = header.read_text(encoding="utf-8")
    for token in (
        "XR_VK_TEXTURE_RGBA8_SNORM",
        "XR_VK_TEXTURE_RG8_UNORM",
        "VK_IMAGE_TYPE_3D",
        "VK_IMAGE_VIEW_TYPE_3D",
        "xr_vk_texture_format_supported",
        "copy.imageExtent.depth = depth",
    ):
        if token not in final and token not in header_final:
            raise RuntimeError(f"resource-format validation missing {token}")
    print("[vulkan-resource-formats] generic 2D/3D UNORM/SNORM texture upload installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extend Vulkan texture uploads with R2-compatible 2D/3D formats.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    extend(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
