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

    bool xr_vk_validate_spirv_descriptor_contract(const xr_vector<u8>& bytes, VkShaderStageFlagBits stage)
    {
        if (!xr_vk_validate_spirv_header(bytes) ||
            (stage != VK_SHADER_STAGE_VERTEX_BIT && stage != VK_SHADER_STAGE_FRAGMENT_BIT))
            return false;

        const u32* words = reinterpret_cast<const u32*>(&bytes[0]);
        const u32 word_count_total = static_cast<u32>(bytes.size() / sizeof(u32));
        xr_vector<xr_vk_spirv_descriptor_decoration> decorations;

        enum
        {
            XR_VK_SPV_OP_DECORATE = 71,
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

            if (opcode == XR_VK_SPV_OP_DECORATE && instruction_words >= 4)
            {
                const u32 target_id = words[offset + 1];
                const u32 decoration = words[offset + 2];
                if (decoration == XR_VK_SPV_DECORATION_BINDING ||
                    decoration == XR_VK_SPV_DECORATION_DESCRIPTOR_SET)
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
            offset += instruction_words;
        }

        for (u32 i = 0; i < decorations.size(); ++i)
        {
            const xr_vk_spirv_descriptor_decoration& item = decorations[i];
            if (!item.has_set || !item.has_binding || item.descriptor_set != 0)
                return false;
            if (stage == VK_SHADER_STAGE_VERTEX_BIT)
            {
                if (item.binding != 0 && item.binding != 2)
                    return false;
            }
            else
            {
                if (item.binding != 0 && item.binding != 1)
                    return false;
            }
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
    if "xr_vk_validate_spirv_descriptor_contract" not in text:
        if marker not in text:
            raise RuntimeError("SPIR-V descriptor contract: sidecar read marker missing")
        text = text.replace(marker, CONTRACT_BLOCK + marker, 1)

    read_old = '''        if (!xr_vk_read_shader_sidecar("vs", key.vertex_shader_identity, vertex_spirv) ||
            !xr_vk_read_shader_sidecar("ps", key.pixel_shader_identity, pixel_spirv))
            return VK_NULL_HANDLE;

'''
    read_new = read_old + '''        if (!xr_vk_validate_spirv_descriptor_contract(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT) ||
            !xr_vk_validate_spirv_descriptor_contract(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT))
            return VK_NULL_HANDLE;

'''
    if "xr_vk_validate_spirv_descriptor_contract(vertex_spirv" not in text:
        if read_old not in text:
            raise RuntimeError("SPIR-V descriptor contract: sidecar materializer read block missing")
        text = text.replace(read_old, read_new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "XR_VK_SPV_OP_DECORATE = 71",
        "XR_VK_SPV_DECORATION_BINDING = 33",
        "XR_VK_SPV_DECORATION_DESCRIPTOR_SET = 34",
        "instruction_words > word_count_total - offset",
        "decorations.size() >= 256",
        "item.descriptor_set != 0",
        "item.binding != 0 && item.binding != 2",
        "item.binding != 0 && item.binding != 1",
        "xr_vk_validate_spirv_descriptor_contract(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT)",
        "xr_vk_validate_spirv_descriptor_contract(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"SPIR-V descriptor contract validation failed: missing {token}")

    print("[vulkan-spv-contract] OpDecorate parser enforces set0: binding0 UBO + binding2 VS textures / binding1 PS textures before pipeline creation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce the RC6 Vulkan descriptor ABI on SPIR-V sidecar shaders.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
