from __future__ import annotations

import argparse
from pathlib import Path


def install_material_descriptors(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan material descriptors require materialized indexed draw source")

    text = source.read_text(encoding="utf-8")

    fn_marker = "    PFN_vkDestroyDescriptorPool g_vkDestroyDescriptorPool = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkAllocateDescriptorSets g_vkAllocateDescriptorSets = NULL;
    PFN_vkFreeDescriptorSets g_vkFreeDescriptorSets = NULL;
    PFN_vkUpdateDescriptorSets g_vkUpdateDescriptorSets = NULL;
    PFN_vkCmdBindDescriptorSets g_vkCmdBindDescriptorSets = NULL;
'''
    if "g_vkAllocateDescriptorSets" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan material descriptors: descriptor function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkDestroyDescriptorPool = NULL;\n"
    clear_block = clear_marker + '''        g_vkAllocateDescriptorSets = NULL;
        g_vkFreeDescriptorSets = NULL;
        g_vkUpdateDescriptorSets = NULL;
        g_vkCmdBindDescriptorSets = NULL;
'''
    if "g_vkAllocateDescriptorSets = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan material descriptors: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkDestroyDescriptorPool);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkAllocateDescriptorSets);
        XR_VK_LOAD_DEVICE(vkFreeDescriptorSets);
        XR_VK_LOAD_DEVICE(vkUpdateDescriptorSets);
        XR_VK_LOAD_DEVICE(vkCmdBindDescriptorSets);
'''
    if "XR_VK_LOAD_DEVICE(vkAllocateDescriptorSets)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan material descriptors: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    bool xr_vk_allocate_material_descriptor(VkBuffer uniform_buffer, VkDeviceSize uniform_offset,
        VkDeviceSize uniform_range, VkImageView image_view, VkImageLayout image_layout, VkSampler sampler,
        VkDescriptorSet& descriptor_set)
    {
        descriptor_set = VK_NULL_HANDLE;
        if (g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE ||
            g_descriptor_set_layout == VK_NULL_HANDLE || uniform_buffer == VK_NULL_HANDLE ||
            !uniform_range || image_view == VK_NULL_HANDLE || sampler == VK_NULL_HANDLE ||
            !g_vkAllocateDescriptorSets || !g_vkUpdateDescriptorSets)
            return false;
        if (image_layout != VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL && image_layout != VK_IMAGE_LAYOUT_GENERAL)
            return false;

        VkDescriptorSetAllocateInfo allocate_info = {};
        allocate_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        allocate_info.descriptorPool = g_descriptor_pool;
        allocate_info.descriptorSetCount = 1;
        allocate_info.pSetLayouts = &g_descriptor_set_layout;
        if (g_vkAllocateDescriptorSets(g_device, &allocate_info, &descriptor_set) != VK_SUCCESS)
            return false;

        VkDescriptorBufferInfo buffer_info = {};
        buffer_info.buffer = uniform_buffer;
        buffer_info.offset = uniform_offset;
        buffer_info.range = uniform_range;
        VkDescriptorImageInfo image_info = {};
        image_info.sampler = sampler;
        image_info.imageView = image_view;
        image_info.imageLayout = image_layout;

        VkWriteDescriptorSet writes[2] = {};
        writes[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[0].dstSet = descriptor_set;
        writes[0].dstBinding = 0;
        writes[0].descriptorCount = 1;
        writes[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        writes[0].pBufferInfo = &buffer_info;
        writes[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[1].dstSet = descriptor_set;
        writes[1].dstBinding = 1;
        writes[1].descriptorCount = 1;
        writes[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        writes[1].pImageInfo = &image_info;
        g_vkUpdateDescriptorSets(g_device, 2, writes, 0, NULL);
        return true;
    }

    void xr_vk_free_material_descriptor(VkDescriptorSet& descriptor_set)
    {
        if (descriptor_set != VK_NULL_HANDLE && g_device != VK_NULL_HANDLE &&
            g_descriptor_pool != VK_NULL_HANDLE && g_vkFreeDescriptorSets)
            g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &descriptor_set);
        descriptor_set = VK_NULL_HANDLE;
    }

    bool xr_vk_bind_material_descriptor(VkCommandBuffer command_buffer, VkDescriptorSet descriptor_set)
    {
        if (command_buffer == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE ||
            g_pipeline_layout == VK_NULL_HANDLE || !g_vkCmdBindDescriptorSets)
            return false;
        g_vkCmdBindDescriptorSets(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, g_pipeline_layout,
            0, 1, &descriptor_set, 0, NULL);
        return true;
    }

'''
    if "xr_vk_allocate_material_descriptor" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan material descriptors: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    packet_marker = '''    struct xr_vk_indexed_draw_packet
    {
        VkPipeline pipeline;
'''
    packet_replacement = '''    struct xr_vk_indexed_draw_packet
    {
        VkPipeline pipeline;
        VkDescriptorSet descriptor_set;
'''
    if "VkDescriptorSet descriptor_set;" not in text:
        if packet_marker not in text:
            raise RuntimeError("Vulkan material descriptors: indexed draw packet marker not found")
        text = text.replace(packet_marker, packet_replacement, 1)

    validation_marker = '''        if (command_buffer == VK_NULL_HANDLE || draw.pipeline == VK_NULL_HANDLE || !draw.index_count ||
            !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed)
            return false;
'''
    validation_replacement = '''        if (command_buffer == VK_NULL_HANDLE || draw.pipeline == VK_NULL_HANDLE ||
            draw.descriptor_set == VK_NULL_HANDLE || !draw.index_count ||
            !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed)
            return false;
'''
    if "draw.descriptor_set == VK_NULL_HANDLE" not in text:
        if validation_marker not in text:
            raise RuntimeError("Vulkan material descriptors: indexed draw validation marker not found")
        text = text.replace(validation_marker, validation_replacement, 1)

    bind_marker = '''        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, draw.pipeline);
        g_vkCmdDrawIndexed(command_buffer, draw.index_count, 1, draw.first_index, draw.vertex_offset_bias, 0);
'''
    bind_replacement = '''        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, draw.pipeline);
        if (!xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set))
            return false;
        g_vkCmdDrawIndexed(command_buffer, draw.index_count, 1, draw.first_index, draw.vertex_offset_bias, 0);
'''
    if "xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set)" not in text:
        if bind_marker not in text:
            raise RuntimeError("Vulkan material descriptors: indexed draw bind marker not found")
        text = text.replace(bind_marker, bind_replacement, 1)

    maker_signature = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, D3DFORMAT index_format,
        D3DPRIMITIVETYPE primitive_type, u32 start_index, u32 primitive_count, s32 base_vertex,
        VkDeviceSize vertex_offset, VkDeviceSize index_stream_offset, xr_vk_indexed_draw_packet& draw)
'''
    maker_replacement = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, VkDescriptorSet descriptor_set,
        D3DFORMAT index_format, D3DPRIMITIVETYPE primitive_type, u32 start_index, u32 primitive_count,
        s32 base_vertex, VkDeviceSize vertex_offset, VkDeviceSize index_stream_offset,
        xr_vk_indexed_draw_packet& draw)
'''
    if "VkPipeline pipeline, VkDescriptorSet descriptor_set" not in text:
        if maker_signature not in text:
            raise RuntimeError("Vulkan material descriptors: topology-aware packet factory signature marker not found")
        text = text.replace(maker_signature, maker_replacement, 1)

    maker_guard = '''        if (pipeline == VK_NULL_HANDLE ||
            !xr_vk_d3d_index_format_to_type(index_format, index_type, index_stride) ||
'''
    maker_guard_replacement = '''        if (pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE ||
            !xr_vk_d3d_index_format_to_type(index_format, index_type, index_stride) ||
'''
    if "pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE" not in text:
        if maker_guard not in text:
            raise RuntimeError("Vulkan material descriptors: packet factory guard marker not found")
        text = text.replace(maker_guard, maker_guard_replacement, 1)

    assign_marker = "        draw.pipeline = pipeline;\n"
    if "        draw.descriptor_set = descriptor_set;\n" not in text:
        if assign_marker not in text:
            raise RuntimeError("Vulkan material descriptors: packet assignment marker not found")
        text = text.replace(assign_marker, assign_marker + "        draw.descriptor_set = descriptor_set;\n", 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "PFN_vkAllocateDescriptorSets", "PFN_vkFreeDescriptorSets", "PFN_vkUpdateDescriptorSets",
        "PFN_vkCmdBindDescriptorSets", "xr_vk_allocate_material_descriptor",
        "VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER", "VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
        "xr_vk_free_material_descriptor", "xr_vk_bind_material_descriptor",
        "VkDescriptorSet descriptor_set;", "draw.descriptor_set == VK_NULL_HANDLE",
        "xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set)",
        "VkPipeline pipeline, VkDescriptorSet descriptor_set",
        "D3DFORMAT index_format, D3DPRIMITIVETYPE primitive_type",
        "xr_vk_d3d_primitive_to_topology(primitive_type, topology)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan material descriptor validation failed: missing {token}")
    print("[vulkan-materials] descriptor allocation/update/free + topology-preserving indexed draw binding installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Vulkan material descriptor allocation and draw binding for RC6.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_material_descriptors(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
