from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    required = (
        "PFN_vkAllocateDescriptorSets g_vkAllocateDescriptorSets",
        "PFN_vkFreeDescriptorSets g_vkFreeDescriptorSets",
        "PFN_vkUpdateDescriptorSets g_vkUpdateDescriptorSets",
        "PFN_vkCmdBindDescriptorSets g_vkCmdBindDescriptorSets",
        "XR_VK_LOAD_DEVICE(vkAllocateDescriptorSets)",
        "XR_VK_LOAD_DEVICE(vkUpdateDescriptorSets)",
        "XR_VK_LOAD_DEVICE(vkCmdBindDescriptorSets)",
        "bool xr_vk_allocate_material_descriptor",
        "writes[0].descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER",
        "writes[1].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER",
        "g_vkUpdateDescriptorSets(g_device, 2, writes, 0, NULL)",
        "bool xr_vk_bind_material_descriptor",
        "g_vkCmdBindDescriptorSets(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, g_pipeline_layout",
        "VkDescriptorSet descriptor_set;",
        "draw.descriptor_set == VK_NULL_HANDLE",
        "xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set)",
        "draw.descriptor_set = descriptor_set",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan material descriptor validation failed: missing {token}")

    record_start = text.find("bool xr_vk_record_indexed_draw")
    record_end = text.find("bool xr_vk_make_indexed_draw_packet", record_start)
    if record_start < 0 or record_end < 0:
        raise RuntimeError("Vulkan material descriptor validation failed: indexed draw function range not found")
    record = text[record_start:record_end]
    order = (
        "g_vkCmdBindPipeline",
        "xr_vk_bind_material_descriptor",
        "g_vkCmdDrawIndexed",
    )
    positions = [record.find(token) for token in order]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise RuntimeError("Vulkan material descriptor validation failed: pipeline/descriptor/draw order is invalid")

    if "descriptor_set == VK_NULL_HANDLE" not in record:
        raise RuntimeError("Vulkan material descriptor validation failed: draw packet permits missing material set")

    print("[validate-vulkan-materials] descriptor lifecycle + bind-before-draw path verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vulkan material descriptor materialization for RC6.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
