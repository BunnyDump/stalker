from __future__ import annotations

import argparse
from pathlib import Path

DESCRIPTOR_CAPACITY = 8192


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    text = text.replace("pool_sizes[0].descriptorCount = 256;", f"pool_sizes[0].descriptorCount = {DESCRIPTOR_CAPACITY};")
    text = text.replace("pool_sizes[1].descriptorCount = 256;", f"pool_sizes[1].descriptorCount = {DESCRIPTOR_CAPACITY};")
    text = text.replace("pool.maxSets = 256;", f"pool.maxSets = {DESCRIPTOR_CAPACITY};")

    state_marker = "    VkDescriptorPool g_descriptor_pool = VK_NULL_HANDLE;\n"
    if "g_material_descriptor_count" not in text:
        if state_marker not in text:
            raise RuntimeError("descriptor pool state marker not found")
        text = text.replace(state_marker, state_marker + f"    u32 g_material_descriptor_count = 0;\n    const u32 g_material_descriptor_capacity = {DESCRIPTOR_CAPACITY};\n", 1)

    alloc_marker = "        if (g_vkAllocateDescriptorSets(g_device, &allocate_info, &descriptor_set) != VK_SUCCESS)\n            return false;\n"
    if "g_material_descriptor_count >= g_material_descriptor_capacity" not in text:
        if alloc_marker not in text:
            raise RuntimeError("descriptor allocation marker not found")
        replacement = (
            "        if (g_material_descriptor_count >= g_material_descriptor_capacity)\n"
            "            return false;\n"
            + alloc_marker +
            "        ++g_material_descriptor_count;\n"
        )
        text = text.replace(alloc_marker, replacement, 1)

    free_marker = "            g_vkFreeDescriptorSets(g_device, g_descriptor_pool, 1, &descriptor_set);\n"
    if "--g_material_descriptor_count" not in text:
        if free_marker not in text:
            raise RuntimeError("descriptor free marker not found")
        text = text.replace(
            free_marker,
            free_marker + "        if (descriptor_set != VK_NULL_HANDLE && g_material_descriptor_count)\n            --g_material_descriptor_count;\n",
            1,
        )

    destroy_marker = "        g_descriptor_pool = VK_NULL_HANDLE;\n"
    if "        g_material_descriptor_count = 0;\n" not in text:
        if destroy_marker not in text:
            raise RuntimeError("descriptor destroy marker not found")
        text = text.replace(destroy_marker, destroy_marker + "        g_material_descriptor_count = 0;\n", 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    for token in (
        f"pool.maxSets = {DESCRIPTOR_CAPACITY};",
        f"const u32 g_material_descriptor_capacity = {DESCRIPTOR_CAPACITY};",
        "g_material_descriptor_count >= g_material_descriptor_capacity",
        "++g_material_descriptor_count",
        "--g_material_descriptor_count",
    ):
        if token not in final:
            raise RuntimeError(f"descriptor capacity hardening missing {token}")
    print(f"[vulkan-descriptors] material descriptor capacity hardened to {DESCRIPTOR_CAPACITY}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
