from __future__ import annotations

import argparse
from pathlib import Path


CONTRACT_BLOCK = r'''    struct xr_vk_spirv_descriptor_decoration
    {
        u32 id;
        u32 descriptor_set;
        u32 binding;
        bool has_set;
        bool has_binding;

        xr_vk_spirv_descriptor_decoration()
            : id(0), descriptor_set(0), binding(0), has_set(false), has_binding(false) {}
    };

    struct xr_vk_spirv_type_info
    {
        u32 opcode;
        u32 storage_class;
        u32 element_type;
        u32 length_id;
        u32 sampled;
        bool block;

        xr_vk_spirv_type_info()
            : opcode(0), storage_class(~0u), element_type(0), length_id(0), sampled(0), block(false) {}
    };

    struct xr_vk_spirv_variable_info
    {
        u32 result_type;
        u32 storage_class;
        bool valid;

        xr_vk_spirv_variable_info() : result_type(0), storage_class(~0u), valid(false) {}
    };

    xr_vk_spirv_descriptor_decoration* xr_vk_find_spirv_descriptor_decoration(
        xr_vector<xr_vk_spirv_descriptor_decoration>& decorations, u32 id)
    {
        for (u32 i = 0; i < decorations.size(); ++i)
            if (decorations[i].id == id)
                return &decorations[i];
        if (decorations.size() >= 256)
            return NULL;
        decorations.push_back(xr_vk_spirv_descriptor_decoration());
        decorations.back().id = id;
        return &decorations.back();
    }

    bool xr_vk_spirv_sampled_image_array(const xr_vector<xr_vk_spirv_type_info>& types,
        const xr_vector<u32>& constants, u32 pointer_type, u32 storage_class, u32 expected_length)
    {
        enum
        {
            XR_VK_SPV_OP_TYPE_IMAGE = 25,
            XR_VK_SPV_OP_TYPE_SAMPLED_IMAGE = 27,
            XR_VK_SPV_OP_TYPE_ARRAY = 28,
            XR_VK_SPV_OP_TYPE_POINTER = 32,
            XR_VK_SPV_STORAGE_UNIFORM_CONSTANT = 0,
        };
        if (storage_class != XR_VK_SPV_STORAGE_UNIFORM_CONSTANT || pointer_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& pointer = types[pointer_type];
        if (pointer.opcode != XR_VK_SPV_OP_TYPE_POINTER ||
            pointer.storage_class != XR_VK_SPV_STORAGE_UNIFORM_CONSTANT || pointer.element_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& array = types[pointer.element_type];
        if (array.opcode != XR_VK_SPV_OP_TYPE_ARRAY || array.length_id >= constants.size() ||
            constants[array.length_id] != expected_length || array.element_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& sampled_image = types[array.element_type];
        if (sampled_image.opcode != XR_VK_SPV_OP_TYPE_SAMPLED_IMAGE || sampled_image.element_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& image = types[sampled_image.element_type];
        return image.opcode == XR_VK_SPV_OP_TYPE_IMAGE && image.sampled == 1;
    }

    bool xr_vk_spirv_uniform_block(const xr_vector<xr_vk_spirv_type_info>& types,
        u32 pointer_type, u32 storage_class)
    {
        enum
        {
            XR_VK_SPV_OP_TYPE_STRUCT = 30,
            XR_VK_SPV_OP_TYPE_POINTER = 32,
            XR_VK_SPV_STORAGE_UNIFORM = 2,
        };
        if (storage_class != XR_VK_SPV_STORAGE_UNIFORM || pointer_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& pointer = types[pointer_type];
        if (pointer.opcode != XR_VK_SPV_OP_TYPE_POINTER || pointer.storage_class != XR_VK_SPV_STORAGE_UNIFORM ||
            pointer.element_type >= types.size())
            return false;
        const xr_vk_spirv_type_info& block = types[pointer.element_type];
        return block.opcode == XR_VK_SPV_OP_TYPE_STRUCT && block.block;
    }

    bool xr_vk_validate_spirv_descriptor_contract(const xr_vector<u8>& bytes, VkShaderStageFlagBits stage)
    {
        if (!xr_vk_validate_spirv_header(bytes) ||
            (stage != VK_SHADER_STAGE_VERTEX_BIT && stage != VK_SHADER_STAGE_FRAGMENT_BIT))
            return false;

        const u32* words = reinterpret_cast<const u32*>(&bytes[0]);
        const u32 word_count_total = static_cast<u32>(bytes.size() / sizeof(u32));
        const u32 id_bound = words[3];
        if (id_bound < 1 || id_bound > 65536)
            return false;

        xr_vector<xr_vk_spirv_descriptor_decoration> decorations;
        xr_vector<xr_vk_spirv_type_info> types(id_bound);
        xr_vector<xr_vk_spirv_variable_info> variables(id_bound);
        xr_vector<u32> constants(id_bound, ~0u);

        enum
        {
            XR_VK_SPV_OP_TYPE_IMAGE = 25,
            XR_VK_SPV_OP_TYPE_SAMPLED_IMAGE = 27,
            XR_VK_SPV_OP_TYPE_ARRAY = 28,
            XR_VK_SPV_OP_TYPE_STRUCT = 30,
            XR_VK_SPV_OP_TYPE_POINTER = 32,
            XR_VK_SPV_OP_CONSTANT = 43,
            XR_VK_SPV_OP_VARIABLE = 59,
            XR_VK_SPV_OP_DECORATE = 71,
            XR_VK_SPV_DECORATION_BLOCK = 2,
            XR_VK_SPV_DECORATION_BINDING = 33,
            XR_VK_SPV_DECORATION_DESCRIPTOR_SET = 34,
        };

        for (u32 offset = 5; offset < word_count_total;)
        {
            const u32 instruction = words[offset];
            const u32 instruction_words = instruction >> 16;
            const u32 opcode = instruction & 0xffffu;
            if (!instruction_words || instruction_words > word_count_total - offset)
                return false;

            if (opcode == XR_VK_SPV_OP_DECORATE && instruction_words >= 3)
            {
                const u32 target_id = words[offset + 1];
                const u32 decoration = words[offset + 2];
                if (target_id >= id_bound)
                    return false;
                if (decoration == XR_VK_SPV_DECORATION_BLOCK)
                    types[target_id].block = true;
                else if ((decoration == XR_VK_SPV_DECORATION_BINDING ||
                          decoration == XR_VK_SPV_DECORATION_DESCRIPTOR_SET) && instruction_words >= 4)
                {
                    xr_vk_spirv_descriptor_decoration* item =
                        xr_vk_find_spirv_descriptor_decoration(decorations, target_id);
                    if (!item)
                        return false;
                    if (decoration == XR_VK_SPV_DECORATION_BINDING)
                    {
                        if (item->has_binding && item->binding != words[offset + 3])
                            return false;
                        item->binding = words[offset + 3];
                        item->has_binding = true;
                    }
                    else
                    {
                        if (item->has_set && item->descriptor_set != words[offset + 3])
                            return false;
                        item->descriptor_set = words[offset + 3];
                        item->has_set = true;
                    }
                }
            }
            else if (opcode == XR_VK_SPV_OP_TYPE_IMAGE && instruction_words >= 9)
            {
                const u32 id = words[offset + 1];
                if (id >= id_bound)
                    return false;
                types[id].opcode = opcode;
                types[id].sampled = words[offset + 7];
            }
            else if (opcode == XR_VK_SPV_OP_TYPE_SAMPLED_IMAGE && instruction_words >= 3)
            {
                const u32 id = words[offset + 1];
                if (id >= id_bound)
                    return false;
                types[id].opcode = opcode;
                types[id].element_type = words[offset + 2];
            }
            else if (opcode == XR_VK_SPV_OP_TYPE_ARRAY && instruction_words >= 4)
            {
                const u32 id = words[offset + 1];
                if (id >= id_bound)
                    return false;
                types[id].opcode = opcode;
                types[id].element_type = words[offset + 2];
                types[id].length_id = words[offset + 3];
            }
            else if (opcode == XR_VK_SPV_OP_TYPE_STRUCT && instruction_words >= 2)
            {
                const u32 id = words[offset + 1];
                if (id >= id_bound)
                    return false;
                types[id].opcode = opcode;
            }
            else if (opcode == XR_VK_SPV_OP_TYPE_POINTER && instruction_words >= 4)
            {
                const u32 id = words[offset + 1];
                if (id >= id_bound)
                    return false;
                types[id].opcode = opcode;
                types[id].storage_class = words[offset + 2];
                types[id].element_type = words[offset + 3];
            }
            else if (opcode == XR_VK_SPV_OP_CONSTANT && instruction_words == 4)
            {
                const u32 id = words[offset + 2];
                if (id >= id_bound)
                    return false;
                constants[id] = words[offset + 3];
            }
            else if (opcode == XR_VK_SPV_OP_VARIABLE && instruction_words >= 4)
            {
                const u32 result_type = words[offset + 1];
                const u32 id = words[offset + 2];
                if (id >= id_bound || result_type >= id_bound)
                    return false;
                variables[id].result_type = result_type;
                variables[id].storage_class = words[offset + 3];
                variables[id].valid = true;
            }
            offset += instruction_words;
        }

        for (u32 i = 0; i < decorations.size(); ++i)
        {
            const xr_vk_spirv_descriptor_decoration& item = decorations[i];
            if (!item.has_set || !item.has_binding || item.descriptor_set != 0 ||
                item.id >= variables.size() || !variables[item.id].valid)
                return false;

            const xr_vk_spirv_variable_info& variable = variables[item.id];
            if (item.binding == 0)
            {
                if (!xr_vk_spirv_uniform_block(types, variable.result_type, variable.storage_class))
                    return false;
            }
            else if (stage == VK_SHADER_STAGE_VERTEX_BIT && item.binding == 2)
            {
                if (!xr_vk_spirv_sampled_image_array(types, constants, variable.result_type,
                        variable.storage_class, XR_VK_VS_TEXTURE_SLOTS))
                    return false;
            }
            else if (stage == VK_SHADER_STAGE_FRAGMENT_BIT && item.binding == 1)
            {
                if (!xr_vk_spirv_sampled_image_array(types, constants, variable.result_type,
                        variable.storage_class, XR_VK_PS_TEXTURE_SLOTS))
                    return false;
            }
            else
                return false;
        }
        return true;
    }

'''


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "xr_vk_validate_spirv_header" not in text or "xr_vk_materialize_backend_pipeline" not in text:
        raise RuntimeError("SPIR-V descriptor contract requires sidecar pipeline materialization")

    marker = "    bool xr_vk_read_spirv_sidecar(const char* path, xr_vector<u8>& bytes)\n"
    start = text.find("    struct xr_vk_spirv_descriptor_decoration\n")
    end = text.find(marker, start)
    if start >= 0:
        if end < 0:
            raise RuntimeError("SPIR-V descriptor contract: existing block end marker missing")
        text = text[:start] + CONTRACT_BLOCK + text[end:]
    else:
        if marker not in text:
            raise RuntimeError("SPIR-V descriptor contract: sidecar read marker missing")
        text = text.replace(marker, CONTRACT_BLOCK + marker, 1)

    read_old = '''        if (!xr_vk_read_shader_sidecar("vs", key.vertex_shader_identity, vertex_spirv) ||
            !xr_vk_read_shader_sidecar("ps", key.pixel_shader_identity, pixel_spirv))
            return VK_NULL_HANDLE;

'''
    read_guard = '''        if (!xr_vk_validate_spirv_descriptor_contract(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT) ||
            !xr_vk_validate_spirv_descriptor_contract(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT))
            return VK_NULL_HANDLE;

'''
    if read_guard not in text:
        if read_old not in text:
            raise RuntimeError("SPIR-V descriptor contract: sidecar materializer read block missing")
        text = text.replace(read_old, read_old + read_guard, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "XR_VK_SPV_OP_TYPE_IMAGE = 25",
        "XR_VK_SPV_OP_TYPE_SAMPLED_IMAGE = 27",
        "XR_VK_SPV_OP_TYPE_ARRAY = 28",
        "XR_VK_SPV_OP_TYPE_STRUCT = 30",
        "XR_VK_SPV_OP_TYPE_POINTER = 32",
        "XR_VK_SPV_OP_CONSTANT = 43",
        "XR_VK_SPV_OP_VARIABLE = 59",
        "XR_VK_SPV_DECORATION_BLOCK = 2",
        "XR_VK_SPV_DECORATION_BINDING = 33",
        "XR_VK_SPV_DECORATION_DESCRIPTOR_SET = 34",
        "id_bound > 65536",
        "xr_vk_spirv_uniform_block",
        "xr_vk_spirv_sampled_image_array",
        "constants[array.length_id] != expected_length",
        "image.sampled == 1",
        "XR_VK_VS_TEXTURE_SLOTS",
        "XR_VK_PS_TEXTURE_SLOTS",
        "xr_vk_validate_spirv_descriptor_contract(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT)",
        "xr_vk_validate_spirv_descriptor_contract(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"SPIR-V descriptor contract validation failed: missing {token}")

    print("[vulkan-spv-contract] set0 decorations + UBO Block type + PS[16]/VS[5] combined sampled-image array types verified before pipeline creation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce the RC6 Vulkan descriptor ABI and SPIR-V resource types on sidecar shaders.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
