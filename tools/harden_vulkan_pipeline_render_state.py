from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    bool xr_vk_compare_op_from_d3d(u32 value, VkCompareOp& out)
    {
        switch ((D3DCMPFUNC)value)
        {
        case D3DCMP_NEVER: out = VK_COMPARE_OP_NEVER; return true;
        case D3DCMP_LESS: out = VK_COMPARE_OP_LESS; return true;
        case D3DCMP_EQUAL: out = VK_COMPARE_OP_EQUAL; return true;
        case D3DCMP_LESSEQUAL: out = VK_COMPARE_OP_LESS_OR_EQUAL; return true;
        case D3DCMP_GREATER: out = VK_COMPARE_OP_GREATER; return true;
        case D3DCMP_NOTEQUAL: out = VK_COMPARE_OP_NOT_EQUAL; return true;
        case D3DCMP_GREATEREQUAL: out = VK_COMPARE_OP_GREATER_OR_EQUAL; return true;
        case D3DCMP_ALWAYS: out = VK_COMPARE_OP_ALWAYS; return true;
        default: return false;
        }
    }

    bool xr_vk_blend_factor_from_d3d(u32 value, VkBlendFactor& out)
    {
        switch ((D3DBLEND)value)
        {
        case D3DBLEND_ZERO: out = VK_BLEND_FACTOR_ZERO; return true;
        case D3DBLEND_ONE: out = VK_BLEND_FACTOR_ONE; return true;
        case D3DBLEND_SRCCOLOR: out = VK_BLEND_FACTOR_SRC_COLOR; return true;
        case D3DBLEND_INVSRCCOLOR: out = VK_BLEND_FACTOR_ONE_MINUS_SRC_COLOR; return true;
        case D3DBLEND_SRCALPHA: out = VK_BLEND_FACTOR_SRC_ALPHA; return true;
        case D3DBLEND_INVSRCALPHA: out = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA; return true;
        case D3DBLEND_DESTALPHA: out = VK_BLEND_FACTOR_DST_ALPHA; return true;
        case D3DBLEND_INVDESTALPHA: out = VK_BLEND_FACTOR_ONE_MINUS_DST_ALPHA; return true;
        case D3DBLEND_DESTCOLOR: out = VK_BLEND_FACTOR_DST_COLOR; return true;
        case D3DBLEND_INVDESTCOLOR: out = VK_BLEND_FACTOR_ONE_MINUS_DST_COLOR; return true;
        case D3DBLEND_SRCALPHASAT: out = VK_BLEND_FACTOR_SRC_ALPHA_SATURATE; return true;
        default: return false;
        }
    }

    bool xr_vk_blend_op_from_d3d(u32 value, VkBlendOp& out)
    {
        switch ((D3DBLENDOP)value)
        {
        case D3DBLENDOP_ADD: out = VK_BLEND_OP_ADD; return true;
        case D3DBLENDOP_SUBTRACT: out = VK_BLEND_OP_SUBTRACT; return true;
        case D3DBLENDOP_REVSUBTRACT: out = VK_BLEND_OP_REVERSE_SUBTRACT; return true;
        case D3DBLENDOP_MIN: out = VK_BLEND_OP_MIN; return true;
        case D3DBLENDOP_MAX: out = VK_BLEND_OP_MAX; return true;
        default: return false;
        }
    }

    bool xr_vk_cull_mode_from_d3d(u32 value, VkCullModeFlags& out)
    {
        switch ((D3DCULL)value)
        {
        case D3DCULL_NONE: out = VK_CULL_MODE_NONE; return true;
        // Vulkan frontFace is CLOCKWISE below, therefore D3D's CW/CCW cull values
        // map to FRONT/BACK respectively.
        case D3DCULL_CW: out = VK_CULL_MODE_FRONT_BIT; return true;
        case D3DCULL_CCW: out = VK_CULL_MODE_BACK_BIT; return true;
        default: return false;
        }
    }

    bool xr_vk_apply_render_state_snapshot(const xr_vk_render_state_snapshot& state,
        VkPipelineRasterizationStateCreateInfo& raster,
        VkPipelineDepthStencilStateCreateInfo& depth,
        VkPipelineColorBlendAttachmentState& blend_attachment)
    {
        const u32 required = XR_VK_RS_ZENABLE | XR_VK_RS_ZWRITEENABLE | XR_VK_RS_ZFUNC |
            XR_VK_RS_ALPHABLENDENABLE | XR_VK_RS_SRCBLEND | XR_VK_RS_DESTBLEND |
            XR_VK_RS_BLENDOP | XR_VK_RS_COLORWRITEENABLE | XR_VK_RS_CULLMODE;
        if ((state.valid_mask & required) != required || !state.identity)
            return false;

        if (state.z_enable == D3DZB_USEW)
            return false;
        if (state.z_enable != D3DZB_FALSE && state.z_enable != D3DZB_TRUE)
            return false;
        depth.depthTestEnable = state.z_enable == D3DZB_TRUE ? VK_TRUE : VK_FALSE;
        depth.depthWriteEnable = state.z_write_enable ? VK_TRUE : VK_FALSE;
        if (!xr_vk_compare_op_from_d3d(state.z_func, depth.depthCompareOp))
            return false;

        if (!xr_vk_cull_mode_from_d3d(state.cull_mode, raster.cullMode))
            return false;

        blend_attachment.blendEnable = state.alpha_blend_enable ? VK_TRUE : VK_FALSE;
        if (blend_attachment.blendEnable)
        {
            if (!xr_vk_blend_factor_from_d3d(state.src_blend, blend_attachment.srcColorBlendFactor) ||
                !xr_vk_blend_factor_from_d3d(state.dest_blend, blend_attachment.dstColorBlendFactor) ||
                !xr_vk_blend_op_from_d3d(state.blend_op, blend_attachment.colorBlendOp))
                return false;
            // SHOC's captured legacy state exposes one RGB blend equation here. Mirror it
            // for alpha until separate alpha blend state is explicitly bridged.
            blend_attachment.srcAlphaBlendFactor = blend_attachment.srcColorBlendFactor;
            blend_attachment.dstAlphaBlendFactor = blend_attachment.dstColorBlendFactor;
            blend_attachment.alphaBlendOp = blend_attachment.colorBlendOp;
        }

        VkColorComponentFlags mask = 0;
        if (state.color_write_enable & D3DCOLORWRITEENABLE_RED) mask |= VK_COLOR_COMPONENT_R_BIT;
        if (state.color_write_enable & D3DCOLORWRITEENABLE_GREEN) mask |= VK_COLOR_COMPONENT_G_BIT;
        if (state.color_write_enable & D3DCOLORWRITEENABLE_BLUE) mask |= VK_COLOR_COMPONENT_B_BIT;
        if (state.color_write_enable & D3DCOLORWRITEENABLE_ALPHA) mask |= VK_COLOR_COMPONENT_A_BIT;
        blend_attachment.colorWriteMask = mask;
        return true;
    }

'''
    if "xr_vk_apply_render_state_snapshot" not in text:
        if helper_marker not in text:
            raise RuntimeError("pipeline render-state: shader helper marker missing")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    old_sig = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout,
        VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST)
'''
    new_sig = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout,
        VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
        const xr_vk_render_state_snapshot* render_state = NULL)
'''
    if "const xr_vk_render_state_snapshot* render_state = NULL" not in text:
        if old_sig not in text:
            raise RuntimeError("pipeline render-state: graphics-pipeline signature marker missing")
        text = text.replace(old_sig, new_sig, 1)

    apply_marker = '''        blend.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO;
        blend.attachmentCount = 1;
        blend.pAttachments = &blend_attachment;
'''
    apply_block = apply_marker + '''        if (render_state && !xr_vk_apply_render_state_snapshot(*render_state, raster, depth, blend_attachment))
        {
            g_vkDestroyShaderModule(g_device, vs, NULL);
            g_vkDestroyShaderModule(g_device, ps, NULL);
            return VK_NULL_HANDLE;
        }
'''
    if "!xr_vk_apply_render_state_snapshot(*render_state" not in text:
        if apply_marker not in text:
            raise RuntimeError("pipeline render-state: blend-state marker missing")
        text = text.replace(apply_marker, apply_block, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_compare_op_from_d3d", "xr_vk_blend_factor_from_d3d", "xr_vk_blend_op_from_d3d",
        "xr_vk_cull_mode_from_d3d", "xr_vk_apply_render_state_snapshot",
        "XR_VK_RS_CULLMODE", "D3DZB_USEW", "D3DCULL_CW", "D3DCULL_CCW",
        "D3DCOLORWRITEENABLE_RED", "const xr_vk_render_state_snapshot* render_state = NULL",
        "!xr_vk_apply_render_state_snapshot(*render_state, raster, depth, blend_attachment)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"pipeline render-state validation failed: missing {token}")

    print("[vulkan-pipeline-render-state] fail-closed D3D9 depth/cull/blend/color-write translation installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate canonical SHOC D3D9 render-state snapshots into Vulkan graphics pipeline state.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
