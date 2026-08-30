from __future__ import annotations

import argparse
from pathlib import Path


def install_pipeline_registry(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan pipeline registry requires materialized command recording")

    text = source.read_text(encoding="utf-8")
    header_text = header.read_text(encoding="utf-8")

    decl_marker = "unsigned xr_vk_bootstrap_physical_device_count();\n"
    decls = (
        "unsigned xr_vk_pipeline_create(const void* vs_data, unsigned vs_size, const char* vs_entry, "
        "const void* ps_data, unsigned ps_size, const char* ps_entry);\n"
        "void xr_vk_pipeline_destroy(unsigned handle);\n"
        "bool xr_vk_pipeline_bind(unsigned handle);\n"
        "bool xr_vk_texture_bind(unsigned handle);\n"
        "bool xr_vk_draw(unsigned vertex_count, unsigned first_vertex);\n"
        + decl_marker
    )
    if "xr_vk_pipeline_create(" not in header_text:
        if decl_marker not in header_text:
            raise RuntimeError("Vulkan pipeline registry: public declaration marker not found")
        header_text = header_text.replace(decl_marker, decls, 1)
        header.write_text(header_text, encoding="utf-8")

    state_marker = "    VkPipelineCache g_pipeline_cache = VK_NULL_HANDLE;\n"
    state_block = state_marker + "    xr_vector<VkPipeline> g_pipelines;\n"
    if "g_pipelines" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: pipeline cache state marker not found")
        text = text.replace(state_marker, state_block, 1)

    fn_marker = "    PFN_vkCmdSetScissor g_vkCmdSetScissor = NULL;\n"
    fn_block = fn_marker + (
        "    PFN_vkCmdBindPipeline g_vkCmdBindPipeline = NULL;\n"
        "    PFN_vkCmdBindDescriptorSets g_vkCmdBindDescriptorSets = NULL;\n"
        "    PFN_vkCmdDraw g_vkCmdDraw = NULL;\n"
    )
    if "g_vkCmdBindPipeline" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: command recording function marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkCmdSetScissor = NULL;\n"
    clear_block = clear_marker + (
        "        g_vkCmdBindPipeline = NULL;\n"
        "        g_vkCmdBindDescriptorSets = NULL;\n"
        "        g_vkCmdDraw = NULL;\n"
    )
    if "g_vkCmdBindPipeline = NULL" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: function clear marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkCmdSetScissor);\n"
    load_block = load_marker + (
        "        XR_VK_LOAD_DEVICE(vkCmdBindPipeline);\n"
        "        XR_VK_LOAD_DEVICE(vkCmdBindDescriptorSets);\n"
        "        XR_VK_LOAD_DEVICE(vkCmdDraw);\n"
    )
    if "XR_VK_LOAD_DEVICE(vkCmdBindPipeline)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: function load marker not found")
        text = text.replace(load_marker, load_block, 1)

    cleanup_marker = "            if (g_pipeline_cache != VK_NULL_HANDLE && g_vkDestroyPipelineCache) g_vkDestroyPipelineCache(g_device, g_pipeline_cache, NULL);\n"
    cleanup = r'''            if (g_vkDestroyPipeline)
            {
                for (u32 i = 0; i < g_pipelines.size(); ++i)
                    if (g_pipelines[i] != VK_NULL_HANDLE)
                        g_vkDestroyPipeline(g_device, g_pipelines[i], NULL);
            }
            g_pipelines.clear();
'''
    if "g_pipelines.clear();" not in text:
        if cleanup_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup + cleanup_marker, 1)

    public_marker = "unsigned xr_vk_bootstrap_physical_device_count()\n"
    public_impl = r'''unsigned xr_vk_pipeline_create(const void* vs_data, unsigned vs_size, const char* vs_entry,
    const void* ps_data, unsigned ps_size, const char* ps_entry)
{
    if (!vs_data || !ps_data || !vs_size || !ps_size || !vs_entry || !ps_entry || g_device == VK_NULL_HANDLE)
        return 0;
    VkPipeline pipeline = xr_vk_create_graphics_pipeline(vs_data, vs_size, vs_entry, ps_data, ps_size, ps_entry);
    if (pipeline == VK_NULL_HANDLE)
        return 0;
    for (u32 i = 0; i < g_pipelines.size(); ++i)
    {
        if (g_pipelines[i] == VK_NULL_HANDLE)
        {
            g_pipelines[i] = pipeline;
            return i + 1;
        }
    }
    g_pipelines.push_back(pipeline);
    return g_pipelines.size();
}

void xr_vk_pipeline_destroy(unsigned handle)
{
    if (!handle || handle > g_pipelines.size())
        return;
    VkPipeline& pipeline = g_pipelines[handle - 1];
    if (pipeline != VK_NULL_HANDLE && g_device != VK_NULL_HANDLE && g_vkDestroyPipeline)
        g_vkDestroyPipeline(g_device, pipeline, NULL);
    pipeline = VK_NULL_HANDLE;
}

bool xr_vk_pipeline_bind(unsigned handle)
{
    if (!g_frame_recording || g_active_command_buffer == VK_NULL_HANDLE ||
        !handle || handle > g_pipelines.size() || !g_vkCmdBindPipeline)
        return false;
    const VkPipeline pipeline = g_pipelines[handle - 1];
    if (pipeline == VK_NULL_HANDLE)
        return false;
    g_vkCmdBindPipeline(g_active_command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    return true;
}

bool xr_vk_texture_bind(unsigned handle)
{
    if (!g_frame_recording || g_active_command_buffer == VK_NULL_HANDLE ||
        !handle || handle > g_textures.size() || !g_vkCmdBindDescriptorSets || g_pipeline_layout == VK_NULL_HANDLE)
        return false;
    const VkDescriptorSet descriptor = g_textures[handle - 1].descriptor_set;
    if (descriptor == VK_NULL_HANDLE)
        return false;
    g_vkCmdBindDescriptorSets(g_active_command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS,
        g_pipeline_layout, 0, 1, &descriptor, 0, NULL);
    return true;
}

bool xr_vk_draw(unsigned vertex_count, unsigned first_vertex)
{
    if (!g_frame_recording || g_active_command_buffer == VK_NULL_HANDLE || !vertex_count || !g_vkCmdDraw)
        return false;
    g_vkCmdDraw(g_active_command_buffer, vertex_count, 1, first_vertex, 0);
    return true;
}

'''
    if "unsigned xr_vk_pipeline_create(const void* vs_data" not in text:
        if public_marker not in text:
            raise RuntimeError("Vulkan pipeline registry: public implementation marker not found")
        text = text.replace(public_marker, public_impl + public_marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_pipeline_create", "xr_vk_pipeline_bind", "xr_vk_texture_bind", "xr_vk_draw",
        "vkCmdBindPipeline", "vkCmdBindDescriptorSets", "vkCmdDraw", "g_pipelines.clear()",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan pipeline registry validation failed: missing {token}")
    print("[vulkan-pipeline-registry] backend-neutral pipeline/texture handles + draw recording installed")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install Vulkan pipeline registry and draw binding API for RC6 xrRender_VK.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    install_pipeline_registry(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
