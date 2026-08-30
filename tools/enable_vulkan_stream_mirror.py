from __future__ import annotations

import argparse
from pathlib import Path


def install_stream_mirror(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan stream mirror requires materialized render core")

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkDeviceMemory g_upload_memory = VK_NULL_HANDLE;\n"
    state_block = state_marker + '''    VkBuffer g_stream_vertex_buffer = VK_NULL_HANDLE;
    VkDeviceMemory g_stream_vertex_memory = VK_NULL_HANDLE;
    VkDeviceSize g_stream_vertex_capacity = 0;
    VkBuffer g_stream_index_buffer = VK_NULL_HANDLE;
    VkDeviceMemory g_stream_index_memory = VK_NULL_HANDLE;
    VkDeviceSize g_stream_index_capacity = 0;
'''
    if "g_stream_vertex_buffer" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan stream mirror: upload-memory state marker not found")
        text = text.replace(state_marker, state_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    void xr_vk_destroy_stream_buffer(VkBuffer& buffer, VkDeviceMemory& memory, VkDeviceSize& capacity)
    {
        if (g_device != VK_NULL_HANDLE && buffer != VK_NULL_HANDLE && g_vkDestroyBuffer)
            g_vkDestroyBuffer(g_device, buffer, NULL);
        if (g_device != VK_NULL_HANDLE && memory != VK_NULL_HANDLE && g_vkFreeMemory)
            g_vkFreeMemory(g_device, memory, NULL);
        buffer = VK_NULL_HANDLE;
        memory = VK_NULL_HANDLE;
        capacity = 0;
    }

    bool xr_vk_resize_host_stream(VkDeviceSize required, VkBufferUsageFlags usage,
        VkBuffer& buffer, VkDeviceMemory& memory, VkDeviceSize& capacity)
    {
        if (!required || g_device == VK_NULL_HANDLE)
            return false;
        if (buffer != VK_NULL_HANDLE && memory != VK_NULL_HANDLE && capacity >= required)
            return true;

        VkDeviceSize new_capacity = capacity ? capacity : 64 * 1024;
        while (new_capacity < required)
            new_capacity *= 2;

        xr_vector<u8> preserved;
        if (memory != VK_NULL_HANDLE && capacity && g_vkMapMemory && g_vkUnmapMemory)
        {
            void* old_data = NULL;
            if (g_vkMapMemory(g_device, memory, 0, capacity, 0, &old_data) == VK_SUCCESS && old_data)
            {
                preserved.resize(static_cast<u32>(capacity));
                CopyMemory(&preserved[0], old_data, static_cast<SIZE_T>(capacity));
                g_vkUnmapMemory(g_device, memory);
            }
        }

        xr_vk_destroy_stream_buffer(buffer, memory, capacity);
        if (!xr_vk_create_buffer(new_capacity, usage,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, buffer, memory))
        {
            xr_vk_destroy_stream_buffer(buffer, memory, capacity);
            return false;
        }
        capacity = new_capacity;

        if (!preserved.empty())
        {
            void* restored = NULL;
            if (g_vkMapMemory(g_device, memory, 0, preserved.size(), 0, &restored) != VK_SUCCESS || !restored)
                return false;
            CopyMemory(restored, &preserved[0], preserved.size());
            g_vkUnmapMemory(g_device, memory);
        }
        return true;
    }

    bool xr_vk_upload_host_stream(const void* data, u32 byte_count, u32 byte_offset,
        VkBufferUsageFlags usage, VkBuffer& buffer, VkDeviceMemory& memory, VkDeviceSize& capacity)
    {
        if (!data || !byte_count)
            return false;
        const VkDeviceSize end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
        if (end < byte_offset || !xr_vk_resize_host_stream(end, usage, buffer, memory, capacity))
            return false;

        void* mapped = NULL;
        if (g_vkMapMemory(g_device, memory, byte_offset, byte_count, 0, &mapped) != VK_SUCCESS || !mapped)
            return false;
        CopyMemory(mapped, data, byte_count);
        g_vkUnmapMemory(g_device, memory);
        return true;
    }

    bool xr_vk_upload_vertex_stream(const void* data, u32 byte_count, u32 byte_offset)
    {
        return xr_vk_upload_host_stream(data, byte_count, byte_offset, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            g_stream_vertex_buffer, g_stream_vertex_memory, g_stream_vertex_capacity);
    }

    bool xr_vk_upload_index_stream(const void* data, u32 byte_count, u32 byte_offset)
    {
        return xr_vk_upload_host_stream(data, byte_count, byte_offset, VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
            g_stream_index_buffer, g_stream_index_memory, g_stream_index_capacity);
    }

    bool xr_vk_bind_stream_geometry(VkCommandBuffer command_buffer, VkDeviceSize vertex_offset,
        VkDeviceSize index_offset, VkIndexType index_type)
    {
        if (command_buffer == VK_NULL_HANDLE || g_stream_vertex_buffer == VK_NULL_HANDLE ||
            g_stream_index_buffer == VK_NULL_HANDLE || !g_vkCmdBindVertexBuffers || !g_vkCmdBindIndexBuffer)
            return false;
        const VkBuffer vertex_buffer = g_stream_vertex_buffer;
        g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vertex_buffer, &vertex_offset);
        g_vkCmdBindIndexBuffer(command_buffer, g_stream_index_buffer, index_offset, index_type);
        return true;
    }

'''
    if "xr_vk_upload_vertex_stream" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan stream mirror: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    destroy_marker = '''        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);
'''
    destroy_block = destroy_marker + '''
        xr_vk_destroy_stream_buffer(g_stream_vertex_buffer, g_stream_vertex_memory, g_stream_vertex_capacity);
        xr_vk_destroy_stream_buffer(g_stream_index_buffer, g_stream_index_memory, g_stream_index_capacity);
'''
    destroy_pos = text.find("void xr_vk_destroy_frame_resources()")
    if "xr_vk_destroy_stream_buffer(g_stream_vertex_buffer" not in text[destroy_pos:]:
        if destroy_pos < 0 or destroy_marker not in text[destroy_pos:]:
            raise RuntimeError("Vulkan stream mirror: frame-resource destroy marker not found")
        prefix = text[:destroy_pos]
        suffix = text[destroy_pos:].replace(destroy_marker, destroy_block, 1)
        text = prefix + suffix

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "g_stream_vertex_buffer",
        "g_stream_index_buffer",
        "xr_vk_resize_host_stream",
        "VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT",
        "xr_vk_upload_host_stream",
        "xr_vk_upload_vertex_stream",
        "VK_BUFFER_USAGE_VERTEX_BUFFER_BIT",
        "xr_vk_upload_index_stream",
        "VK_BUFFER_USAGE_INDEX_BUFFER_BIT",
        "xr_vk_bind_stream_geometry",
        "g_vkCmdBindVertexBuffers(command_buffer, 0, 1",
        "g_vkCmdBindIndexBuffer(command_buffer, g_stream_index_buffer",
        "xr_vk_destroy_stream_buffer(g_stream_vertex_buffer",
        "xr_vk_destroy_stream_buffer(g_stream_index_buffer",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan stream mirror validation failed: missing {token}")

    print("[vulkan-stream-mirror] host-visible vertex/index mirrors + safe bind helper installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Vulkan mirrors for SHOC dynamic vertex/index stream uploads.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_stream_mirror(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())