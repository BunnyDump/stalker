from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan pass descriptors require the materialized resource layer")

    text = source.read_text(encoding="utf-8")
    header_text = header.read_text(encoding="utf-8")

    decl_marker = "bool xr_vk_uniform_write(const void* data, unsigned size, unsigned offset);\n"
    declarations = decl_marker + (
        "unsigned xr_vk_pass_descriptors_create(const unsigned* texture_handles, unsigned texture_count);\n"
        "void xr_vk_pass_descriptors_destroy(unsigned handle);\n"
    )
    if "xr_vk_pass_descriptors_create" not in header_text:
        if decl_marker not in header_text:
            raise RuntimeError("pass-descriptor header marker not found")
        header_text = header_text.replace(decl_marker, declarations, 1)
        header.write_text(header_text, encoding="utf-8")

    state_marker = "    xr_vector<XrVkTexture> g_textures;\n"
    state_block = state_marker + r'''    struct XrVkPassDescriptors
    {
        VkDescriptorSet set;
        XrVkPassDescriptors() : set(VK_NULL_HANDLE) {}
    };
    xr_vector<XrVkPassDescriptors> g_pass_descriptors;
'''
    if "struct XrVkPassDescriptors" not in text:
        if state_marker not in text:
            raise RuntimeError("pass-descriptor state marker not found")
        text = text.replace(state_marker, state_block, 1)

    old_layout = r'''        VkDescriptorSetLayoutBinding bindings[2] = {};
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
    new_layout = r'''        VkDescriptorSetLayoutBinding bindings[9] = {};
        bindings[0].binding = 0;
        bindings[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        bindings[0].descriptorCount = 1;
        bindings[0].stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
        for (u32 binding = 1; binding <= 8; ++binding)
        {
            bindings[binding].binding = binding;
            bindings[binding].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            bindings[binding].descriptorCount = 1;
            bindings[binding].stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
        }
        VkDescriptorSetLayoutCreateInfo descriptor_layout = {};
        descriptor_layout.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        descriptor_layout.bindingCount = 9;
        descriptor_layout.pBindings = bindings;
'''
    if "bindings[9]" not in text:
        if old_layout not in text:
            raise RuntimeError("pass-descriptor layout marker not found")
        text = text.replace(old_layout, new_layout, 1)

    text = text.replace("pool_sizes[0].descriptorCount = 256;", "pool_sizes[0].descriptorCount = 512;", 1)
    text = text.replace("pool_sizes[1].descriptorCount = 256;", "pool_sizes[1].descriptorCount = 4096;", 1)
    text = text.replace("pool.maxSets = 256;", "pool.maxSets = 512;", 1)

    public_marker = "unsigned xr_vk_bootstrap_physical_device_count()\n"
    public_impl = r'''unsigned xr_vk_pass_descriptors_create(const unsigned* texture_handles, unsigned texture_count)
{
    if (texture_count > 8 || (texture_count && !texture_handles) || g_device == VK_NULL_HANDLE ||
        g_descriptor_pool == VK_NULL_HANDLE || g_descriptor_set_layout == VK_NULL_HANDLE ||
        g_uniform_buffer == VK_NULL_HANDLE || !g_vkAllocateDescriptorSets || !g_vkUpdateDescriptorSets)
        return 0;

    VkDescriptorSet set = VK_NULL_HANDLE;
    VkDescriptorSetAllocateInfo allocation = {};
    allocation.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    allocation.descriptorPool = g_descriptor_pool;
    allocation.descriptorSetCount = 1;
    allocation.pSetLayouts = &g_descriptor_set_layout;
    if (g_vkAllocateDescriptorSets(g_device, &allocation, &set) != VK_SUCCESS)
        return 0;

    VkDescriptorBufferInfo uniform = {g_uniform_buffer, 0, 64 * 1024};
    VkDescriptorImageInfo images[8] = {};
    VkWriteDescriptorSet writes[9] = {};
    writes[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    writes[0].dstSet = set;
    writes[0].dstBinding = 0;
    writes[0].descriptorCount = 1;
    writes[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    writes[0].pBufferInfo = &uniform;

    for (u32 i = 0; i < texture_count; ++i)
    {
        const unsigned handle = texture_handles[i];
        if (!handle || handle > g_textures.size())
        {
            g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &set);
            return 0;
        }
        const XrVkTexture& texture = g_textures[handle - 1];
        if (texture.image == VK_NULL_HANDLE || texture.view == VK_NULL_HANDLE)
        {
            g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &set);
            return 0;
        }
        images[i].sampler = g_default_sampler;
        images[i].imageView = texture.view;
        images[i].imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
        writes[i + 1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[i + 1].dstSet = set;
        writes[i + 1].dstBinding = i + 1;
        writes[i + 1].descriptorCount = 1;
        writes[i + 1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        writes[i + 1].pImageInfo = &images[i];
    }
    g_vkUpdateDescriptorSets(g_device, texture_count + 1, writes, 0, NULL);

    XrVkPassDescriptors pass;
    pass.set = set;
    for (u32 i = 0; i < g_pass_descriptors.size(); ++i)
    {
        if (g_pass_descriptors[i].set == VK_NULL_HANDLE)
        {
            g_pass_descriptors[i] = pass;
            return i + 1;
        }
    }
    g_pass_descriptors.push_back(pass);
    return g_pass_descriptors.size();
}

void xr_vk_pass_descriptors_destroy(unsigned handle)
{
    if (!handle || handle > g_pass_descriptors.size())
        return;
    XrVkPassDescriptors& pass = g_pass_descriptors[handle - 1];
    if (pass.set != VK_NULL_HANDLE && g_device != VK_NULL_HANDLE && g_descriptor_pool != VK_NULL_HANDLE && g_vkFreeDescriptorSets)
        g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &pass.set);
    pass.set = VK_NULL_HANDLE;
}

'''
    if "unsigned xr_vk_pass_descriptors_create" not in text:
        if public_marker not in text:
            raise RuntimeError("pass-descriptor public implementation marker not found")
        text = text.replace(public_marker, public_impl + public_marker, 1)

    cleanup_marker = "            for (u32 i = 0; i < g_textures.size(); ++i)\n                xr_vk_destroy_texture_object(g_textures[i]);\n"
    cleanup = r'''            for (u32 i = 0; i < g_pass_descriptors.size(); ++i)
            {
                if (g_pass_descriptors[i].set != VK_NULL_HANDLE && g_descriptor_pool != VK_NULL_HANDLE && g_vkFreeDescriptorSets)
                    g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &g_pass_descriptors[i].set);
            }
            g_pass_descriptors.clear();
'''
    if "g_pass_descriptors.clear();" not in text:
        if cleanup_marker not in text:
            raise RuntimeError("pass-descriptor cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup + cleanup_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    header_final = header.read_text(encoding="utf-8")
    for token in (
        "VkDescriptorSetLayoutBinding bindings[9]",
        "descriptor_layout.bindingCount = 9",
        "pool_sizes[1].descriptorCount = 4096",
        "xr_vk_pass_descriptors_create",
        "writes[i + 1].dstBinding = i + 1",
        "g_pass_descriptors.clear()",
    ):
        if token not in final and token not in header_final:
            raise RuntimeError(f"pass-descriptor validation missing {token}")
    print("[vulkan-pass-descriptors] fixed UBO=0 + sampler=1..8 layout and pass descriptor sets installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install fixed R2 Vulkan descriptor binding contract and pass-level descriptor sets.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
