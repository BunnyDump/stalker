from __future__ import annotations

import argparse
from pathlib import Path


BLOCK = r'''    struct xr_vk_pipeline_texture_usage
    {
        VkPipeline pipeline;
        u32 pixel_mask;
        u32 vertex_mask;
    };

    xr_vector<xr_vk_pipeline_texture_usage> g_pipeline_texture_usage;

    bool xr_vk_collect_spirv_texture_usage(const xr_vector<u8>& bytes, VkShaderStageFlagBits stage, u32& mask)
    {
        mask = 0;
        if (!xr_vk_validate_spirv_header(bytes) ||
            (stage != VK_SHADER_STAGE_VERTEX_BIT && stage != VK_SHADER_STAGE_FRAGMENT_BIT))
            return false;

        const u32* words = reinterpret_cast<const u32*>(&bytes[0]);
        const u32 word_count_total = static_cast<u32>(bytes.size() / sizeof(u32));
        const u32 id_bound = words[3];
        if (id_bound < 1 || id_bound > 65536)
            return false;

        xr_vector<u32> bindings(id_bound, ~0u);
        xr_vector<u32> sets(id_bound, ~0u);
        xr_vector<u32> constants(id_bound, ~0u);
        xr_vector<u8> variables(id_bound, 0);

        enum
        {
            XR_VK_SPV_OP_NAME = 5,
            XR_VK_SPV_OP_ENTRY_POINT = 15,
            XR_VK_SPV_OP_CONSTANT = 43,
            XR_VK_SPV_OP_VARIABLE = 59,
            XR_VK_SPV_OP_LOAD = 61,
            XR_VK_SPV_OP_ACCESS_CHAIN = 65,
            XR_VK_SPV_OP_IN_BOUNDS_ACCESS_CHAIN = 66,
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
                const u32 target = words[offset + 1];
                if (target >= id_bound)
                    return false;
                if (words[offset + 2] == XR_VK_SPV_DECORATION_BINDING)
                    bindings[target] = words[offset + 3];
                else if (words[offset + 2] == XR_VK_SPV_DECORATION_DESCRIPTOR_SET)
                    sets[target] = words[offset + 3];
            }
            else if (opcode == XR_VK_SPV_OP_CONSTANT && instruction_words == 4)
            {
                const u32 result = words[offset + 2];
                if (result >= id_bound)
                    return false;
                constants[result] = words[offset + 3];
            }
            else if (opcode == XR_VK_SPV_OP_VARIABLE && instruction_words >= 4)
            {
                const u32 result = words[offset + 2];
                if (result >= id_bound)
                    return false;
                variables[result] = 1;
            }
            offset += instruction_words;
        }

        const u32 texture_binding = stage == VK_SHADER_STAGE_VERTEX_BIT ? 2u : 1u;
        const u32 texture_slots = stage == VK_SHADER_STAGE_VERTEX_BIT ? XR_VK_VS_TEXTURE_SLOTS : XR_VK_PS_TEXTURE_SLOTS;
        const u32 full_mask = (1u << texture_slots) - 1u;
        u32 texture_variable = 0;
        for (u32 id = 1; id < id_bound; ++id)
        {
            if (!variables[id] || sets[id] != 0 || bindings[id] != texture_binding)
                continue;
            if (texture_variable)
                return false;
            texture_variable = id;
        }
        if (!texture_variable)
            return true;

        for (u32 offset = 5; offset < word_count_total;)
        {
            const u32 instruction = words[offset];
            const u32 instruction_words = instruction >> 16;
            const u32 opcode = instruction & 0xffffu;
            if (!instruction_words || instruction_words > word_count_total - offset)
                return false;

            if ((opcode == XR_VK_SPV_OP_ACCESS_CHAIN || opcode == XR_VK_SPV_OP_IN_BOUNDS_ACCESS_CHAIN) &&
                instruction_words >= 5 && words[offset + 3] == texture_variable)
            {
                const u32 index_id = words[offset + 4];
                if (index_id >= constants.size() || constants[index_id] == ~0u)
                    mask |= full_mask;
                else if (constants[index_id] >= texture_slots)
                    return false;
                else
                    mask |= 1u << constants[index_id];
            }
            else if (opcode == XR_VK_SPV_OP_LOAD && instruction_words >= 4 && words[offset + 3] == texture_variable)
                mask |= full_mask;
            else if (opcode != XR_VK_SPV_OP_DECORATE && opcode != XR_VK_SPV_OP_NAME &&
                     opcode != XR_VK_SPV_OP_ENTRY_POINT && opcode != XR_VK_SPV_OP_VARIABLE)
            {
                for (u32 operand = 1; operand < instruction_words; ++operand)
                    if (words[offset + operand] == texture_variable)
                    {
                        mask |= full_mask;
                        break;
                    }
            }
            offset += instruction_words;
        }
        return (mask & ~full_mask) == 0;
    }

    void xr_vk_record_pipeline_texture_usage(VkPipeline pipeline, u32 pixel_mask, u32 vertex_mask)
    {
        if (pipeline == VK_NULL_HANDLE)
            return;
        for (u32 i = 0; i < g_pipeline_texture_usage.size(); ++i)
        {
            if (g_pipeline_texture_usage[i].pipeline != pipeline)
                continue;
            g_pipeline_texture_usage[i].pixel_mask = pixel_mask;
            g_pipeline_texture_usage[i].vertex_mask = vertex_mask;
            return;
        }
        xr_vk_pipeline_texture_usage usage;
        usage.pipeline = pipeline;
        usage.pixel_mask = pixel_mask;
        usage.vertex_mask = vertex_mask;
        g_pipeline_texture_usage.push_back(usage);
    }

    bool xr_vk_find_pipeline_texture_usage(VkPipeline pipeline, u32& pixel_mask, u32& vertex_mask)
    {
        pixel_mask = 0;
        vertex_mask = 0;
        if (pipeline == VK_NULL_HANDLE || !xr_vk_pipeline_is_current(pipeline))
            return false;
        for (u32 i = 0; i < g_pipeline_texture_usage.size(); ++i)
        {
            if (g_pipeline_texture_usage[i].pipeline != pipeline)
                continue;
            pixel_mask = g_pipeline_texture_usage[i].pixel_mask;
            vertex_mask = g_pipeline_texture_usage[i].vertex_mask;
            return true;
        }
        return false;
    }

'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def harden(root: Path) -> None:
    source = Path(root).resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    for token in ("xr_vk_validate_spirv_descriptor_contract", "xr_vk_materialize_backend_pipeline", "xr_vk_pipeline_is_current"):
        if token not in text:
            raise RuntimeError(f"SPIR-V texture usage requires {token}")

    marker = "    bool xr_vk_read_spirv_sidecar(const char* path, xr_vector<u8>& bytes)\n"
    if "struct xr_vk_pipeline_texture_usage" not in text:
        if marker not in text:
            raise RuntimeError("SPIR-V texture usage: sidecar reader marker missing")
        text = text.replace(marker, BLOCK + marker, 1)

    validation = '''        if (!xr_vk_validate_spirv_descriptor_contract(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT) ||
            !xr_vk_validate_spirv_descriptor_contract(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT))
            return VK_NULL_HANDLE;

'''
    usage = validation + '''        u32 vertex_texture_mask = 0;
        u32 pixel_texture_mask = 0;
        if (!xr_vk_collect_spirv_texture_usage(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT, vertex_texture_mask) ||
            !xr_vk_collect_spirv_texture_usage(pixel_spirv, VK_SHADER_STAGE_FRAGMENT_BIT, pixel_texture_mask))
            return VK_NULL_HANDLE;

'''
    if "u32 vertex_texture_mask = 0;" not in text:
        text = replace_once(text, validation, usage, "SPIR-V texture usage materializer")

    register_old = '''        if (!xr_vk_register_backend_pipeline(key, pipeline))
        {
            xr_vk_destroy_pipeline_handle(pipeline);
            return VK_NULL_HANDLE;
        }
        return pipeline;
'''
    register_new = '''        if (!xr_vk_register_backend_pipeline(key, pipeline))
        {
            xr_vk_destroy_pipeline_handle(pipeline);
            return VK_NULL_HANDLE;
        }
        xr_vk_record_pipeline_texture_usage(pipeline, pixel_texture_mask, vertex_texture_mask);
        return pipeline;
'''
    if "xr_vk_record_pipeline_texture_usage(pipeline, pixel_texture_mask, vertex_texture_mask);" not in text:
        text = replace_once(text, register_old, register_new, "pipeline texture usage registration")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    for token in (
        "XR_VK_SPV_OP_ACCESS_CHAIN = 65",
        "XR_VK_SPV_OP_IN_BOUNDS_ACCESS_CHAIN = 66",
        "const u32 full_mask = (1u << texture_slots) - 1u;",
        "mask |= 1u << constants[index_id];",
        "mask |= full_mask;",
        "xr_vk_record_pipeline_texture_usage",
        "xr_vk_find_pipeline_texture_usage",
        "xr_vk_record_pipeline_texture_usage(pipeline, pixel_texture_mask, vertex_texture_mask);",
    ):
        if token not in final:
            raise RuntimeError(f"SPIR-V texture usage validation failed: missing {token}")
    print("[vulkan-spv-usage] conservative static/dynamic texture-array usage masks recorded per materialized pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive conservative PS/VS descriptor element usage masks from SPIR-V sidecars.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
