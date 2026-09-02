from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    legacy_sig = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout)
'''
    topology_sig = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout, VkPrimitiveTopology topology)
'''
    hardened_sig = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout,
        VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST)
'''

    if hardened_sig not in text:
        if topology_sig in text:
            text = text.replace(topology_sig, hardened_sig, 1)
        elif legacy_sig in text:
            text = text.replace(legacy_sig, hardened_sig, 1)
        elif "VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST" not in text:
            raise RuntimeError("Vulkan pipeline topology: graphics-pipeline signature marker not found")

    old_guard = '''        if (g_render_pass == VK_NULL_HANDLE || g_pipeline_layout == VK_NULL_HANDLE ||
            !vs_entry || !ps_entry || !g_vkCreateGraphicsPipelines)
            return VK_NULL_HANDLE;
'''
    new_guard = '''        if (g_render_pass == VK_NULL_HANDLE || g_pipeline_layout == VK_NULL_HANDLE ||
            !vs_entry || !ps_entry || !g_vkCreateGraphicsPipelines ||
            topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM)
            return VK_NULL_HANDLE;
'''
    if "topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM" not in text and "topology < VK_PRIMITIVE_TOPOLOGY_POINT_LIST" not in text:
        if old_guard not in text:
            raise RuntimeError("Vulkan pipeline topology: factory guard marker not found")
        text = text.replace(old_guard, new_guard, 1)

    old_assignment = "        input_assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;\n"
    new_assignment = "        input_assembly.topology = topology;\n"
    if new_assignment not in text:
        if old_assignment not in text:
            raise RuntimeError("Vulkan pipeline topology: hard-coded topology marker not found")
        text = text.replace(old_assignment, new_assignment, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST",
        "input_assembly.topology = topology;",
        "xr_vk_d3d_primitive_to_topology",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan pipeline topology validation failed: missing {token}")
    if "topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM" not in final and "topology < VK_PRIMITIVE_TOPOLOGY_POINT_LIST" not in final:
        raise RuntimeError("Vulkan pipeline topology validation failed: fail-closed topology guard missing")

    factory_start = final.find("VkPipeline xr_vk_create_graphics_pipeline")
    factory_end = final.find("bool xr_vk_create_render_core()", factory_start)
    if factory_start < 0 or factory_end < 0:
        raise RuntimeError("Vulkan pipeline topology validation failed: factory boundary not found")
    factory = final[factory_start:factory_end]
    if "input_assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;" in factory:
        raise RuntimeError("Vulkan pipeline topology validation failed: hard-coded triangle-list assignment remains")

    print("[vulkan-pipeline-topology] topology-aware pipeline factory is idempotent with the SGeometry adapter")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden RC6 Vulkan graphics pipeline creation after SGeometry topology translation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
