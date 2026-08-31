from __future__ import annotations

import argparse
from pathlib import Path


PS_SLOTS = 16
VS_SLOTS = 5
DESCRIPTOR_SETS = 8192


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "xr_vk_texture_resource_shader_readable" not in text:
        raise RuntimeError("21-slot descriptor schema requires texture owner/resource hardening first")

    layout_old = '''        VkDescriptorSetLayoutBinding bindings[2] = {};
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
'''
    layout_new = f'''        VkDescriptorSetLayoutBinding bindings[3] = {{}};
        bindings[0].binding = 0;
        bindings[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        bindings[0].descriptorCount = 1;
        bindings[0].stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
        bindings[1].binding = 1;
        bindings[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        bindings[1].descriptorCount = {PS_SLOTS};
        bindings[1].stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT;
        bindings[2].binding = 2;
        bindings[2].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        bindings[2].descriptorCount = {VS_SLOTS};
        bindings[2].stageFlags = VK_SHADER_STAGE_VERTEX_BIT;
        VkDescriptorSetLayoutCreateInfo descriptor_layout = {{}};
        descriptor_layout.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        descriptor_layout.bindingCount = 3;
        descriptor_layout.pBindings = bindings;
'''
    if "bindings[2].binding = 2;" not in text:
        if layout_old not in text:
            raise RuntimeError("21-slot descriptor schema: legacy layout marker missing")
        text = text.replace(layout_old, layout_new, 1)

    pool_old = f"        pool_sizes[1].descriptorCount = {DESCRIPTOR_SETS};\n"
    pool_new = f"        pool_sizes[1].descriptorCount = {DESCRIPTOR_SETS * (PS_SLOTS + VS_SLOTS)};\n"
    if pool_new not in text:
        if pool_old not in text:
            raise RuntimeError("21-slot descriptor schema: hardened pool marker missing")
        text = text.replace(pool_old, pool_new, 1)

    helper_marker = "    bool xr_vk_allocate_material_descriptor(VkBuffer uniform_buffer, VkDeviceSize uniform_offset,\n"
    constants = f'''    enum {{ XR_VK_PS_TEXTURE_SLOTS = {PS_SLOTS}, XR_VK_VS_TEXTURE_SLOTS = {VS_SLOTS}, XR_VK_TEXTURE_SLOTS = {PS_SLOTS + VS_SLOTS} }};\n\n'''
    if "XR_VK_PS_TEXTURE_SLOTS" not in text:
        if helper_marker not in text:
            raise RuntimeError("21-slot descriptor schema: material allocation marker missing")
        text = text.replace(helper_marker, constants + helper_marker, 1)

    free_marker = "    void xr_vk_free_material_descriptor(VkDescriptorSet& descriptor_set)\n"
    snapshot_helper = r'''    bool xr_vk_allocate_snapshot_descriptor(VkBuffer uniform_buffer, VkDeviceSize uniform_offset,
        VkDeviceSize uniform_range, const xr_vk_texture_resource* const* pixel_resources,
        const xr_vk_texture_resource* const* vertex_resources, VkSampler sampler, VkDescriptorSet& descriptor_set)
    {
        descriptor_set = VK_NULL_HANDLE;
        if (g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE ||
            g_descriptor_set_layout == VK_NULL_HANDLE || uniform_buffer == VK_NULL_HANDLE || !uniform_range ||
            !pixel_resources || !vertex_resources || sampler == VK_NULL_HANDLE ||
            !g_vkAllocateDescriptorSets || !g_vkUpdateDescriptorSets)
            return false;

        for (u32 i = 0; i < XR_VK_PS_TEXTURE_SLOTS; ++i)
            if (pixel_resources[i] && !xr_vk_texture_resource_shader_readable(pixel_resources[i]))
                return false;
        for (u32 i = 0; i < XR_VK_VS_TEXTURE_SLOTS; ++i)
            if (vertex_resources[i] && !xr_vk_texture_resource_shader_readable(vertex_resources[i]))
                return false;

        if (g_material_descriptor_count >= g_material_descriptor_capacity)
            return false;

        VkDescriptorSetAllocateInfo allocate_info = {};
        allocate_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        allocate_info.descriptorPool = g_descriptor_pool;
        allocate_info.descriptorSetCount = 1;
        allocate_info.pSetLayouts = &g_descriptor_set_layout;
        if (g_vkAllocateDescriptorSets(g_device, &allocate_info, &descriptor_set) != VK_SUCCESS)
            return false;
        ++g_material_descriptor_count;

        VkDescriptorBufferInfo buffer_info = {};
        buffer_info.buffer = uniform_buffer;
        buffer_info.offset = uniform_offset;
        buffer_info.range = uniform_range;

        VkDescriptorImageInfo image_infos[XR_VK_TEXTURE_SLOTS] = {};
        VkWriteDescriptorSet writes[1 + XR_VK_TEXTURE_SLOTS] = {};
        u32 write_count = 0;

        writes[write_count].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[write_count].dstSet = descriptor_set;
        writes[write_count].dstBinding = 0;
        writes[write_count].descriptorCount = 1;
        writes[write_count].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        writes[write_count].pBufferInfo = &buffer_info;
        ++write_count;

        u32 image_index = 0;
        for (u32 i = 0; i < XR_VK_PS_TEXTURE_SLOTS; ++i)
        {
            const xr_vk_texture_resource* resource = pixel_resources[i];
            if (!resource)
                continue;
            VkDescriptorImageInfo& image = image_infos[image_index++];
            image.sampler = sampler;
            image.imageView = resource->view;
            image.imageLayout = resource->layout;
            VkWriteDescriptorSet& write = writes[write_count++];
            write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
            write.dstSet = descriptor_set;
            write.dstBinding = 1;
            write.dstArrayElement = i;
            write.descriptorCount = 1;
            write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            write.pImageInfo = &image;
        }

        for (u32 i = 0; i < XR_VK_VS_TEXTURE_SLOTS; ++i)
        {
            const xr_vk_texture_resource* resource = vertex_resources[i];
            if (!resource)
                continue;
            VkDescriptorImageInfo& image = image_infos[image_index++];
            image.sampler = sampler;
            image.imageView = resource->view;
            image.imageLayout = resource->layout;
            VkWriteDescriptorSet& write = writes[write_count++];
            write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
            write.dstSet = descriptor_set;
            write.dstBinding = 2;
            write.dstArrayElement = i;
            write.descriptorCount = 1;
            write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            write.pImageInfo = &image;
        }

        g_vkUpdateDescriptorSets(g_device, write_count, writes, 0, NULL);
        return true;
    }

'''
    if "xr_vk_allocate_snapshot_descriptor" not in text:
        if free_marker not in text:
            raise RuntimeError("21-slot descriptor schema: descriptor free marker missing")
        text = text.replace(free_marker, snapshot_helper + free_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "VkDescriptorSetLayoutBinding bindings[3]",
        f"bindings[1].descriptorCount = {PS_SLOTS};",
        f"bindings[2].descriptorCount = {VS_SLOTS};",
        "bindings[2].stageFlags = VK_SHADER_STAGE_VERTEX_BIT;",
        "descriptor_layout.bindingCount = 3;",
        f"pool_sizes[1].descriptorCount = {DESCRIPTOR_SETS * (PS_SLOTS + VS_SLOTS)};",
        "XR_VK_PS_TEXTURE_SLOTS = 16",
        "XR_VK_VS_TEXTURE_SLOTS = 5",
        "xr_vk_allocate_snapshot_descriptor",
        "write.dstBinding = 1;",
        "write.dstBinding = 2;",
        "write.dstArrayElement = i;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"21-slot descriptor schema validation failed: missing {token}")

    print("[vulkan-descriptor-schema] set0: UBO + PS[16] + VS[5] descriptor arrays materialized; sparse slots remain unwritten/fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize the SHOC 16 PS + 5 VS Vulkan texture descriptor schema.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
