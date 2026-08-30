from __future__ import annotations

import argparse
from pathlib import Path


def install_dds_upload(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("DDS upload requires materialized Vulkan resource layer")

    h = header.read_text(encoding="utf-8")
    marker = "unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height);\n"
    if "xr_vk_texture_create_dds" not in h:
        if marker not in h:
            raise RuntimeError("DDS upload header marker missing")
        h = h.replace(marker, marker + "unsigned xr_vk_texture_create_dds(const void* data, unsigned size);\n", 1)
        header.write_text(h, encoding="utf-8")

    text = source.read_text(encoding="utf-8")
    public_marker = "unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height)\n"
    impl = r'''namespace
{
    static unsigned xr_vk_dds_u32(const u8* p)
    {
        return unsigned(p[0]) | (unsigned(p[1]) << 8) | (unsigned(p[2]) << 16) | (unsigned(p[3]) << 24);
    }

    static unsigned xr_vk_dds_level_size(VkFormat format, unsigned width, unsigned height)
    {
        if (format == VK_FORMAT_BC1_RGBA_UNORM_BLOCK)
            return _max(1u, (width + 3u) / 4u) * _max(1u, (height + 3u) / 4u) * 8u;
        if (format == VK_FORMAT_BC2_UNORM_BLOCK || format == VK_FORMAT_BC3_UNORM_BLOCK)
            return _max(1u, (width + 3u) / 4u) * _max(1u, (height + 3u) / 4u) * 16u;
        return width * height * 4u;
    }

    static bool xr_vk_create_host_staging(VkDeviceSize size, VkBuffer& buffer, VkDeviceMemory& memory)
    {
        buffer = VK_NULL_HANDLE;
        memory = VK_NULL_HANDLE;
        return xr_vk_create_buffer(size, VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, buffer, memory);
    }

    static bool xr_vk_upload_dds_image(VkImage image, VkBuffer staging,
        const xr_vector<VkBufferImageCopy>& copies, unsigned mip_count)
    {
        VkCommandBufferAllocateInfo alloc = {};
        alloc.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        alloc.commandPool = g_command_pool;
        alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        alloc.commandBufferCount = 1;
        VkCommandBuffer cmd = VK_NULL_HANDLE;
        if (g_vkAllocateCommandBuffers(g_device, &alloc, &cmd) != VK_SUCCESS)
            return false;

        VkCommandBufferBeginInfo begin = {};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        if (g_vkBeginCommandBuffer(cmd, &begin) != VK_SUCCESS)
        {
            g_vkFreeCommandBuffers(g_device, g_command_pool, 1, &cmd);
            return false;
        }

        VkImageMemoryBarrier barrier = {};
        barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        barrier.srcAccessMask = 0;
        barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        barrier.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = image;
        barrier.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        barrier.subresourceRange.baseMipLevel = 0;
        barrier.subresourceRange.levelCount = mip_count;
        barrier.subresourceRange.baseArrayLayer = 0;
        barrier.subresourceRange.layerCount = 1;
        g_vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0,
            0, NULL, 0, NULL, 1, &barrier);

        g_vkCmdCopyBufferToImage(cmd, staging, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            copies.size(), copies.empty() ? NULL : &copies[0]);

        barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
        barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        barrier.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
        g_vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0,
            0, NULL, 0, NULL, 1, &barrier);

        bool ok = g_vkEndCommandBuffer(cmd) == VK_SUCCESS;
        if (ok)
        {
            VkSubmitInfo submit = {};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &cmd;
            ok = g_vkQueueSubmit(g_graphics_queue, 1, &submit, VK_NULL_HANDLE) == VK_SUCCESS;
            if (ok) ok = g_vkQueueWaitIdle(g_graphics_queue) == VK_SUCCESS;
        }
        g_vkFreeCommandBuffers(g_device, g_command_pool, 1, &cmd);
        return ok;
    }
}

unsigned xr_vk_texture_create_dds(const void* data, unsigned size)
{
    if (!data || size < 128 || g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE)
        return 0;
    const u8* bytes = reinterpret_cast<const u8*>(data);
    if (xr_vk_dds_u32(bytes) != 0x20534444u || xr_vk_dds_u32(bytes + 4) != 124u || xr_vk_dds_u32(bytes + 76) != 32u)
        return 0;

    const unsigned height = xr_vk_dds_u32(bytes + 12);
    const unsigned width = xr_vk_dds_u32(bytes + 16);
    unsigned mip_count = xr_vk_dds_u32(bytes + 28);
    if (!mip_count) mip_count = 1;
    if (!width || !height || mip_count > 16)
        return 0;

    const unsigned pf_flags = xr_vk_dds_u32(bytes + 80);
    const unsigned fourcc = xr_vk_dds_u32(bytes + 84);
    const unsigned rgb_bits = xr_vk_dds_u32(bytes + 88);
    const unsigned rmask = xr_vk_dds_u32(bytes + 92);
    const unsigned gmask = xr_vk_dds_u32(bytes + 96);
    const unsigned bmask = xr_vk_dds_u32(bytes + 100);
    const unsigned amask = xr_vk_dds_u32(bytes + 104);
    const unsigned caps2 = xr_vk_dds_u32(bytes + 112);
    if (caps2 & 0x00000200u) // DDSCAPS2_CUBEMAP: handled by the cube path, not the 2D loader.
        return 0;

    VkFormat format = VK_FORMAT_UNDEFINED;
    if (pf_flags & 0x4u)
    {
        if (fourcc == 0x31545844u) format = VK_FORMAT_BC1_RGBA_UNORM_BLOCK; // DXT1
        else if (fourcc == 0x33545844u) format = VK_FORMAT_BC2_UNORM_BLOCK; // DXT3
        else if (fourcc == 0x35545844u) format = VK_FORMAT_BC3_UNORM_BLOCK; // DXT5
    }
    else if (rgb_bits == 32)
    {
        if (rmask == 0x00ff0000u && gmask == 0x0000ff00u && bmask == 0x000000ffu && amask == 0xff000000u)
            format = VK_FORMAT_B8G8R8A8_UNORM;
        else if (rmask == 0x000000ffu && gmask == 0x0000ff00u && bmask == 0x00ff0000u && amask == 0xff000000u)
            format = VK_FORMAT_R8G8B8A8_UNORM;
    }
    if (format == VK_FORMAT_UNDEFINED)
        return 0;

    xr_vector<VkBufferImageCopy> copies;
    copies.reserve(mip_count);
    unsigned offset = 128;
    unsigned w = width, hgt = height;
    for (unsigned level = 0; level < mip_count; ++level)
    {
        const unsigned level_size = xr_vk_dds_level_size(format, w, hgt);
        if (offset > size || level_size > size - offset)
            return 0;
        VkBufferImageCopy copy = {};
        copy.bufferOffset = offset - 128;
        copy.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        copy.imageSubresource.mipLevel = level;
        copy.imageSubresource.baseArrayLayer = 0;
        copy.imageSubresource.layerCount = 1;
        copy.imageExtent.width = w;
        copy.imageExtent.height = hgt;
        copy.imageExtent.depth = 1;
        copies.push_back(copy);
        offset += level_size;
        w = _max(1u, w >> 1);
        hgt = _max(1u, hgt >> 1);
    }
    const unsigned payload_size = offset - 128;
    if (!payload_size)
        return 0;

    VkBuffer staging = VK_NULL_HANDLE;
    VkDeviceMemory staging_memory = VK_NULL_HANDLE;
    if (!xr_vk_create_host_staging(payload_size, staging, staging_memory))
        return 0;
    void* mapped = NULL;
    if (g_vkMapMemory(g_device, staging_memory, 0, payload_size, 0, &mapped) != VK_SUCCESS || !mapped)
    {
        if (staging != VK_NULL_HANDLE) g_vkDestroyBuffer(g_device, staging, NULL);
        if (staging_memory != VK_NULL_HANDLE) g_vkFreeMemory(g_device, staging_memory, NULL);
        return 0;
    }
    Memory.mem_copy(mapped, bytes + 128, payload_size);
    g_vkUnmapMemory(g_device, staging_memory);

    XrVkTexture texture;
    texture.width = width;
    texture.height = height;
    VkImageCreateInfo image_info = {};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = format;
    image_info.extent.width = width;
    image_info.extent.height = height;
    image_info.extent.depth = 1;
    image_info.mipLevels = mip_count;
    image_info.arrayLayers = 1;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
    image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    bool ok = g_vkCreateImage(g_device, &image_info, NULL, &texture.image) == VK_SUCCESS;
    if (ok)
    {
        VkMemoryRequirements req = {};
        g_vkGetImageMemoryRequirements(g_device, texture.image, &req);
        const unsigned mt = xr_vk_find_memory_type(req.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        VkMemoryAllocateInfo alloc = {};
        alloc.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        alloc.allocationSize = req.size;
        alloc.memoryTypeIndex = mt;
        ok = mt != ~0u && g_vkAllocateMemory(g_device, &alloc, NULL, &texture.memory) == VK_SUCCESS &&
            g_vkBindImageMemory(g_device, texture.image, texture.memory, 0) == VK_SUCCESS;
    }
    if (ok)
    {
        VkImageViewCreateInfo view = {};
        view.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        view.image = texture.image;
        view.viewType = VK_IMAGE_VIEW_TYPE_2D;
        view.format = format;
        view.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        view.subresourceRange.levelCount = mip_count;
        view.subresourceRange.layerCount = 1;
        ok = g_vkCreateImageView(g_device, &view, NULL, &texture.view) == VK_SUCCESS;
    }
    if (ok)
        ok = xr_vk_upload_dds_image(texture.image, staging, copies, mip_count);

    g_vkDestroyBuffer(g_device, staging, NULL);
    g_vkFreeMemory(g_device, staging_memory, NULL);
    if (!ok)
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
        if (g_textures[i].image == VK_NULL_HANDLE) { g_textures[i] = texture; return i + 1; }
    g_textures.push_back(texture);
    return g_textures.size();
}

'''
    if "unsigned xr_vk_texture_create_dds(" not in text:
        if public_marker not in text:
            raise RuntimeError("DDS upload implementation marker missing")
        text = text.replace(public_marker, impl + public_marker, 1)
        source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    for token in ("VK_FORMAT_BC1_RGBA_UNORM_BLOCK", "VK_FORMAT_BC2_UNORM_BLOCK", "VK_FORMAT_BC3_UNORM_BLOCK",
                  "xr_vk_texture_create_dds", "VkBufferImageCopy", "mip_count"):
        if token not in final:
            raise RuntimeError(f"DDS upload validation missing {token}")
    print("[vulkan-dds] native DDS 2D upload supports BC1/BC2/BC3, BGRA/RGBA and full mip chains")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install native Vulkan DDS 2D texture upload support.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    install_dds_upload(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
