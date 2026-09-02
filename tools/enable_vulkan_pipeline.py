from __future__ import annotations

import argparse
from pathlib import Path


def install_pipeline(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan pipeline layer requires materialized render core")

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkPipelineLayout g_pipeline_layout = VK_NULL_HANDLE;\n"
    state_block = state_marker + "    VkPipelineCache g_pipeline_cache = VK_NULL_HANDLE;\n"
    if "g_pipeline_cache" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan pipeline: pipeline-layout state marker not found")
        text = text.replace(state_marker, state_block, 1)

    fn_marker = "    PFN_vkDestroyPipelineLayout g_vkDestroyPipelineLayout = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkCreateShaderModule g_vkCreateShaderModule = NULL;
    PFN_vkDestroyShaderModule g_vkDestroyShaderModule = NULL;
    PFN_vkCreatePipelineCache g_vkCreatePipelineCache = NULL;
    PFN_vkDestroyPipelineCache g_vkDestroyPipelineCache = NULL;
    PFN_vkCreateGraphicsPipelines g_vkCreateGraphicsPipelines = NULL;
    PFN_vkDestroyPipeline g_vkDestroyPipeline = NULL;
'''
    if "g_vkCreateShaderModule" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan pipeline: function table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkDestroyPipelineLayout = NULL;\n"
    clear_block = clear_marker + '''        g_vkCreateShaderModule = NULL;
        g_vkDestroyShaderModule = NULL;
        g_vkCreatePipelineCache = NULL;
        g_vkDestroyPipelineCache = NULL;
        g_vkCreateGraphicsPipelines = NULL;
        g_vkDestroyPipeline = NULL;
'''
    if "g_vkCreateShaderModule = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan pipeline: clear function marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkDestroyPipelineLayout);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCreateShaderModule);
        XR_VK_LOAD_DEVICE(vkDestroyShaderModule);
        XR_VK_LOAD_DEVICE(vkCreatePipelineCache);
        XR_VK_LOAD_DEVICE(vkDestroyPipelineCache);
        XR_VK_LOAD_DEVICE(vkCreateGraphicsPipelines);
        XR_VK_LOAD_DEVICE(vkDestroyPipeline);
'''
    if "XR_VK_LOAD_DEVICE(vkCreateShaderModule)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan pipeline: device load marker not found")
        text = text.replace(load_marker, load_block, 1)

    helper_marker = "    bool xr_vk_create_render_core()\n    {\n"
    helpers = r'''    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)
    {
        if (!data || size < 20 || (size & 3) || g_device == VK_NULL_HANDLE || !g_vkCreateShaderModule)
            return VK_NULL_HANDLE;
        const u32* words = static_cast<const u32*>(data);
        if (words[0] != 0x07230203u)
            return VK_NULL_HANDLE;
        VkShaderModuleCreateInfo info = {};
        info.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        info.codeSize = size;
        info.pCode = words;
        VkShaderModule module = VK_NULL_HANDLE;
        if (g_vkCreateShaderModule(g_device, &info, NULL, &module) != VK_SUCCESS)
            return VK_NULL_HANDLE;
        return module;
    }

    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry)
    {
        if (g_render_pass == VK_NULL_HANDLE || g_pipeline_layout == VK_NULL_HANDLE ||
            !vs_entry || !ps_entry || !g_vkCreateGraphicsPipelines)
            return VK_NULL_HANDLE;

        VkShaderModule vs = xr_vk_create_shader_module(vs_data, vs_size);
        VkShaderModule ps = xr_vk_create_shader_module(ps_data, ps_size);
        if (vs == VK_NULL_HANDLE || ps == VK_NULL_HANDLE)
        {
            if (vs != VK_NULL_HANDLE) g_vkDestroyShaderModule(g_device, vs, NULL);
            if (ps != VK_NULL_HANDLE) g_vkDestroyShaderModule(g_device, ps, NULL);
            return VK_NULL_HANDLE;
        }

        VkPipelineShaderStageCreateInfo stages[2] = {};
        stages[0].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
        stages[0].module = vs;
        stages[0].pName = vs_entry;
        stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
        stages[1].module = ps;
        stages[1].pName = ps_entry;

        VkPipelineVertexInputStateCreateInfo vertex_input = {};
        vertex_input.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO;
        VkPipelineInputAssemblyStateCreateInfo input_assembly = {};
        input_assembly.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO;
        input_assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
        VkPipelineViewportStateCreateInfo viewport = {};
        viewport.sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO;
        viewport.viewportCount = 1;
        viewport.scissorCount = 1;
        VkPipelineRasterizationStateCreateInfo raster = {};
        raster.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO;
        raster.polygonMode = VK_POLYGON_MODE_FILL;
        raster.cullMode = VK_CULL_MODE_BACK_BIT;
        raster.frontFace = VK_FRONT_FACE_CLOCKWISE;
        raster.lineWidth = 1.0f;
        VkPipelineMultisampleStateCreateInfo multisample = {};
        multisample.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO;
        multisample.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
        VkPipelineDepthStencilStateCreateInfo depth = {};
        depth.sType = VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO;
        depth.depthTestEnable = VK_TRUE;
        depth.depthWriteEnable = VK_TRUE;
        depth.depthCompareOp = VK_COMPARE_OP_LESS_OR_EQUAL;
        VkPipelineColorBlendAttachmentState blend_attachment = {};
        blend_attachment.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT |
            VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
        VkPipelineColorBlendStateCreateInfo blend = {};
        blend.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO;
        blend.attachmentCount = 1;
        blend.pAttachments = &blend_attachment;
        const VkDynamicState dynamic_states[] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
        VkPipelineDynamicStateCreateInfo dynamic = {};
        dynamic.sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO;
        dynamic.dynamicStateCount = sizeof(dynamic_states) / sizeof(dynamic_states[0]);
        dynamic.pDynamicStates = dynamic_states;

        VkGraphicsPipelineCreateInfo info = {};
        info.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO;
        info.stageCount = 2;
        info.pStages = stages;
        info.pVertexInputState = &vertex_input;
        info.pInputAssemblyState = &input_assembly;
        info.pViewportState = &viewport;
        info.pRasterizationState = &raster;
        info.pMultisampleState = &multisample;
        info.pDepthStencilState = &depth;
        info.pColorBlendState = &blend;
        info.pDynamicState = &dynamic;
        info.layout = g_pipeline_layout;
        info.renderPass = g_render_pass;
        info.subpass = 0;
        VkPipeline pipeline = VK_NULL_HANDLE;
        const VkResult result = g_vkCreateGraphicsPipelines(g_device, g_pipeline_cache, 1, &info, NULL, &pipeline);
        g_vkDestroyShaderModule(g_device, vs, NULL);
        g_vkDestroyShaderModule(g_device, ps, NULL);
        return result == VK_SUCCESS ? pipeline : VK_NULL_HANDLE;
    }

'''
    if "VkShaderModule xr_vk_create_shader_module" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan pipeline: render-core helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    create_marker = "        if (g_vkCreatePipelineLayout(g_device, &pipeline_layout, NULL, &g_pipeline_layout) != VK_SUCCESS)\n            return false;\n"
    create_replacement = create_marker + '''
        VkPipelineCacheCreateInfo pipeline_cache_info = {};
        pipeline_cache_info.sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO;
        if (g_vkCreatePipelineCache(g_device, &pipeline_cache_info, NULL, &g_pipeline_cache) != VK_SUCCESS)
            return false;
'''
    if "g_vkCreatePipelineCache(g_device" not in text:
        if create_marker not in text:
            raise RuntimeError("Vulkan pipeline: pipeline-layout creation marker not found")
        text = text.replace(create_marker, create_replacement, 1)

    cleanup_marker = "            if (g_pipeline_layout != VK_NULL_HANDLE && g_vkDestroyPipelineLayout) g_vkDestroyPipelineLayout(g_device, g_pipeline_layout, NULL);\n"
    cleanup_replacement = "            if (g_pipeline_cache != VK_NULL_HANDLE && g_vkDestroyPipelineCache) g_vkDestroyPipelineCache(g_device, g_pipeline_cache, NULL);\n" + cleanup_marker
    if "g_vkDestroyPipelineCache(g_device, g_pipeline_cache" not in text:
        if cleanup_marker not in text:
            raise RuntimeError("Vulkan pipeline: cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup_replacement, 1)

    reset_marker = "        g_pipeline_layout = VK_NULL_HANDLE;\n"
    if "        g_pipeline_cache = VK_NULL_HANDLE;\n" not in text[text.find("void xr_vk_destroy_frame_resources"):]:
        if reset_marker not in text:
            raise RuntimeError("Vulkan pipeline: state reset marker not found")
        text = text.replace(reset_marker, "        g_pipeline_cache = VK_NULL_HANDLE;\n" + reset_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "vkCreateShaderModule", "vkDestroyShaderModule", "vkCreatePipelineCache",
        "vkCreateGraphicsPipelines", "VkGraphicsPipelineCreateInfo", "VK_DYNAMIC_STATE_VIEWPORT",
        "0x07230203u",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan pipeline validation failed: missing {token}")
    print("[vulkan-pipeline] SPIR-V shader modules + pipeline cache + base graphics pipeline factory installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install native Vulkan shader/pipeline infrastructure for RC6 xrRender_VK.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_pipeline(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
