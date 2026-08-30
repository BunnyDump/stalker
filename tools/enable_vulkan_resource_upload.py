from __future__ import annotations

import argparse
from pathlib import Path


def install_resource_upload(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan resource upload requires materialized pipeline layer")

    text = source.read_text(encoding="utf-8")
    header_text = header.read_text(encoding="utf-8")

    decl_marker = "unsigned xr_vk_bootstrap_physical_device_count();\n"
    decls = decl_marker + (
        "unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height);\n"
        "void xr_vk_texture_destroy(unsigned handle);\n"
        "bool xr_vk_uniform_write(const void* data, unsigned size, unsigned offset);\n"
    )
    if "xr_vk_texture_create_rgba8" not in header_text:
        if decl_marker not in header_text:
            raise RuntimeError("Vulkan resources: public declaration marker not found")
        header_text = header_text.replace(decl_marker, decls, 1)
        header.write_text(header_text, encoding="utf-8")

    state_marker = "    xr_vector<VkFramebuffer> g_framebuffers;\n"
    state_block = state_marker + r'''    struct XrVkTexture
    {
        VkImage image;
        VkDeviceMemory memory;
        VkImageView view;
        VkDescriptorSet descriptor_set;
        unsigned width;
        unsigned height;
        XrVkTexture() : image(VK_NULL_HANDLE), memory(VK_NULL_HANDLE), view(VK_NULL_HANDLE),
            descriptor_set(VK_NULL_HANDLE), width(0), height(0) {}
    };
    xr_vector<XrVkTexture> g_textures;
'''
    if "struct XrVkTexture" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan resources: state marker not found")
        text = text.replace(state_marker, state_block, 1)

    fn_marker = "    PFN_vkUnmapMemory g_vkUnmapMemory = NULL;\n"
    fn_block = fn_marker + r'''    PFN_vkAllocateDescriptorSets g_vkAllocateDescriptorSets = NULL;
    PFN_vkFreeDescriptorSets g_vkFreeDescriptorSets = NULL;
    PFN_vkUpdateDescriptorSets g_vkUpdateDescriptorSets = NULL;
    PFN_vkCmdCopyBufferToImage g_vkCmdCopyBufferToImage = NULL;
    PFN_vkFreeCommandBuffers g_vkFreeCommandBuffers = NULL;
    PFN_vkQueueWaitIdle g_vkQueueWaitIdle = NULL;
'''
    if "g_vkAllocateDescriptorSets" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan resources: function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkUnmapMemory = NULL;\n"
    clear_block = clear_marker + r'''        g_vkAllocateDescriptorSets = NULL;
        g_vkFreeDescriptorSets = NULL;
        g_vkUpdateDescriptorSets = NULL;
        g_vkCmdCopyBufferToImage = NULL;
        g_vkFreeCommandBuffers = NULL;
        g_vkQueueWaitIdle = NULL;
'''
    if "g_vkAllocateDescriptorSets = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan resources: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkUnmapMemory);\n"
    load_block = load_marker + r'''        XR_VK_LOAD_DEVICE(vkAllocateDescriptorSets);
        XR_VK_LOAD_DEVICE(vkFreeDescriptorSets);
        XR_VK_LOAD_DEVICE(vkUpdateDescriptorSets);
        XR_VK_LOAD_DEVICE(vkCmdCopyBufferToImage);
        XR_VK_LOAD_DEVICE(vkFreeCommandBuffers);
        XR_VK_LOAD_DEVICE(vkQueueWaitIdle);
'''
    if "XR_VK_LOAD_DEVICE(vkAllocateDescriptorSets)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan resources: load marker not found")
        text = text.replace(load_marker, load_block, 1)

    helper_marker = "    bool xr_vk_create_render_core()\n    {\n"
    helpers = r'''    void xr_vk_destroy_texture_object(XrVkTexture& texture)
    {
        if (g_device != VK_NULL_HANDLE)
        {
            if (texture.descriptor_set != VK_NULL_HANDLE && g_descriptor_pool != VK_NULL_HANDLE && g_vkFreeDescriptorSets)
                g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &texture.descriptor_set);
            if (texture.view != VK_NULL_HANDLE && g_vkDestroyImageView)
                g_vkDestroyImageView(g_device, texture.view, NULL);
            if (texture.image != VK_NULL_HANDLE && g_vkDestroyImage)
                g_vkDestroyImage(g_device, texture.image, NULL);
            if (texture.memory != VK_NULL_HANDLE && g_vkFreeMemory)
                g_vkFreeMemory(g_device, texture.memory, NULL);
        }
        texture = XrVkTexture();
    }

    bool xr_vk_submit_texture_upload(VkImage image, unsigned width, unsigned height)
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

        VkImageMemoryBarrier to_transfer = {};
        to_transfer.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        to_transfer.srcAccessMask = 0;
        to_transfer.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        to_transfer.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        to_transfer.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        to_transfer.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        to_transfer.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        to_transfer.image = image;
        to_transfer.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        to_transfer.subresourceRange.levelCount = 1;
        to_transfer.subresourceRange.layerCount = 1;
        g_vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0,
            0, NULL, 0, NULL, 1, &to_transfer);

        VkBufferImageCopy copy = {};
        copy.bufferOffset = 0;
        copy.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        copy.imageSubresource.mipLevel = 0;
        copy.imageSubresource.baseArrayLayer = 0;
        copy.imageSubresource.layerCount = 1;
        copy.imageExtent.width = width;
        copy.imageExtent.height = height;
        copy.imageExtent.depth = 1;
        g_vkCmdCopyBufferToImage(cmd, g_upload_buffer, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);

        VkImageMemoryBarrier to_shader = to_transfer;
        to_shader.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        to_shader.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
        to_shader.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        to_shader.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
        g_vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0,
            0, NULL, 0, NULL, 1, &to_shader);

        if (g_vkEndCommandBuffer(cmd) != VK_SUCCESS)
        {
            g_vkFreeCommandBuffers(g_device, g_command_pool, 1, &cmd);
            return false;
        }
        VkSubmitInfo submit = {};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &cmd;
        const VkResult result = g_vkQueueSubmit(g_graphics_queue, 1, &submit, VK_NULL_HANDLE);
        if (result == VK_SUCCESS)
            g_vkQueueWaitIdle(g_graphics_queue);
        g_vkFreeCommandBuffers(g_device, g_command_pool, 1, &cmd);
        return result == VK_SUCCESS;
    }

'''
    if "xr_vk_submit_texture_upload" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan resources: render-core marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    public_marker = "unsigned xr_vk_bootstrap_physical_device_count()\n"
    public_impl = r'''unsigned xr_vk_texture_create_rgba8(const void* pixels, unsigned width, unsigned height)
{
    if (!pixels || !width || !height || g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE)
        return 0;
    const u64 byte_count = u64(width) * u64(height) * 4ull;
    if (byte_count > 4ull * 1024ull * 1024ull)
        return 0;

    void* mapped = NULL;
    if (g_vkMapMemory(g_device, g_upload_memory, 0, VkDeviceSize(byte_count), 0, &mapped) != VK_SUCCESS || !mapped)
        return 0;
    Memory.mem_copy(mapped, pixels, size_t(byte_count));
    g_vkUnmapMemory(g_device, g_upload_memory);

    XrVkTexture texture;
    texture.width = width;
    texture.height = height;
    VkImageCreateInfo image_info = {};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.format = VK_FORMAT_R8G8B8A8_UNORM;
    image_info.extent.width = width;
    image_info.extent.height = height;
    image_info.extent.depth = 1;
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
    view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view_info.format = VK_FORMAT_R8G8B8A8_UNORM;
    view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    view_info.subresourceRange.levelCount = 1;
    view_info.subresourceRange.layerCount = 1;
    if (g_vkCreateImageView(g_device, &view_info, NULL, &texture.view) != VK_SUCCESS ||
        !xr_vk_submit_texture_upload(texture.image, width, height))
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

void xr_vk_texture_destroy(unsigned handle)
{
    if (!handle || handle > g_textures.size())
        return;
    xr_vk_destroy_texture_object(g_textures[handle - 1]);
}

bool xr_vk_uniform_write(const void* data, unsigned size, unsigned offset)
{
    if (!data || !size || offset > 64 * 1024 || size > 64 * 1024 - offset || g_uniform_memory == VK_NULL_HANDLE)
        return false;
    void* mapped = NULL;
    if (g_vkMapMemory(g_device, g_uniform_memory, offset, size, 0, &mapped) != VK_SUCCESS || !mapped)
        return false;
    Memory.mem_copy(mapped, data, size);
    g_vkUnmapMemory(g_device, g_uniform_memory);
    return true;
}

'''
    if "unsigned xr_vk_texture_create_rgba8" not in text:
        if public_marker not in text:
            raise RuntimeError("Vulkan resources: public implementation marker not found")
        text = text.replace(public_marker, public_impl + public_marker, 1)

    cleanup_marker = "            if (g_default_sampler != VK_NULL_HANDLE && g_vkDestroySampler) g_vkDestroySampler(g_device, g_default_sampler, NULL);\n"
    cleanup = r'''            for (u32 i = 0; i < g_textures.size(); ++i)
                xr_vk_destroy_texture_object(g_textures[i]);
            g_textures.clear();
'''
    if "xr_vk_destroy_texture_object(g_textures[i])" not in text:
        if cleanup_marker not in text:
            raise RuntimeError("Vulkan resources: cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup + cleanup_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    for token in (
        "vkAllocateDescriptorSets", "vkUpdateDescriptorSets", "vkCmdCopyBufferToImage",
        "VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT",
        "VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL", "xr_vk_texture_create_rgba8", "xr_vk_uniform_write",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan resource validation failed: missing {token}")
    print("[vulkan-resources] RGBA8 texture upload + descriptor allocation/update + uniform write path installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Vulkan image upload and descriptor resource path for RC6 xrRender_VK.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_resource_upload(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
