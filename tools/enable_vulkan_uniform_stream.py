from __future__ import annotations

import argparse
from pathlib import Path

from harden_vulkan_constant_cache_readback import harden as harden_vulkan_constant_cache_readback
from harden_vulkan_constant_snapshot import harden as harden_vulkan_constant_snapshot


UNIFORM_CAPACITY = 64 * 1024


def install_uniform_stream(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan uniform stream requires materialized texture/material state")

    # The Vulkan UBO serializer reads SHOC's float-register cache through const-safe accessors.
    harden_vulkan_constant_cache_readback(root)

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkDeviceMemory g_uniform_memory = VK_NULL_HANDLE;\n"
    state_block = state_marker + f'''    VkDeviceSize g_uniform_cursor = 0;
    const VkDeviceSize g_uniform_capacity = {UNIFORM_CAPACITY};
'''
    if "g_uniform_cursor" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan uniform stream: uniform-memory state marker not found")
        text = text.replace(state_marker, state_block, 1)

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    VkDeviceSize xr_vk_align_uniform_offset(VkDeviceSize value, VkDeviceSize alignment)
    {
        if (alignment <= 1)
            return value;
        const VkDeviceSize remainder = value % alignment;
        if (!remainder)
            return value;
        const VkDeviceSize delta = alignment - remainder;
        if (value > (~VkDeviceSize(0) - delta))
            return ~VkDeviceSize(0);
        return value + delta;
    }

    VkDeviceSize xr_vk_uniform_alignment()
    {
        if (g_selected_physical_device == VK_NULL_HANDLE || !g_vkGetInstanceProcAddr)
            return 1;
        PFN_vkGetPhysicalDeviceProperties get_properties =
            reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(
                g_vkGetInstanceProcAddr(g_vulkan_instance, "vkGetPhysicalDeviceProperties"));
        if (!get_properties)
            return 1;
        VkPhysicalDeviceProperties properties = {};
        get_properties(g_selected_physical_device, &properties);
        const VkDeviceSize alignment = properties.limits.minUniformBufferOffsetAlignment;
        return alignment ? alignment : 1;
    }

    void xr_vk_reset_uniform_stream()
    {
        g_uniform_cursor = 0;
    }

    bool xr_vk_upload_uniform_block(const void* data, VkDeviceSize size, VkDeviceSize& offset)
    {
        offset = 0;
        if (!data || !size || g_device == VK_NULL_HANDLE || g_uniform_memory == VK_NULL_HANDLE ||
            g_uniform_buffer == VK_NULL_HANDLE || !g_vkMapMemory || !g_vkUnmapMemory)
            return false;

        const VkDeviceSize aligned = xr_vk_align_uniform_offset(g_uniform_cursor, xr_vk_uniform_alignment());
        if (aligned == ~VkDeviceSize(0) || aligned > g_uniform_capacity || size > g_uniform_capacity - aligned)
            return false;

        void* mapped = NULL;
        if (g_vkMapMemory(g_device, g_uniform_memory, aligned, size, 0, &mapped) != VK_SUCCESS || !mapped)
            return false;
        memcpy(mapped, data, static_cast<size_t>(size));
        g_vkUnmapMemory(g_device, g_uniform_memory);

        offset = aligned;
        g_uniform_cursor = aligned + size;
        return true;
    }

'''
    if "xr_vk_upload_uniform_block" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan uniform stream: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    frame_marker = "bool xr_vk_bootstrap_frame()\n"
    fence_marker = '''    if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
        return false;
'''
    fence_replacement = fence_marker + '''    // The completed frame no longer references its uniform ranges.
    xr_vk_reset_uniform_stream();
'''
    frame_offset = text.find(frame_marker)
    if frame_offset < 0:
        raise RuntimeError("Vulkan uniform stream: bootstrap-frame marker not found")
    frame_text = text[frame_offset:]
    if "xr_vk_reset_uniform_stream();" not in frame_text:
        fence_offset = frame_text.find(fence_marker)
        if fence_offset < 0:
            raise RuntimeError("Vulkan uniform stream: frame-fence marker not found")
        absolute_fence_offset = frame_offset + fence_offset
        text = (
            text[:absolute_fence_offset]
            + fence_replacement
            + text[absolute_fence_offset + len(fence_marker) :]
        )

    reset_marker = "        g_uniform_memory = VK_NULL_HANDLE;\n"
    if "        g_uniform_cursor = 0;\n" not in text[text.find("void xr_vk_destroy_frame_resources"):]:
        if reset_marker not in text:
            raise RuntimeError("Vulkan uniform stream: render-core reset marker not found")
        text = text.replace(reset_marker, reset_marker + "        g_uniform_cursor = 0;\n", 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "VkDeviceSize g_uniform_cursor",
        f"const VkDeviceSize g_uniform_capacity = {UNIFORM_CAPACITY}",
        "xr_vk_align_uniform_offset",
        "minUniformBufferOffsetAlignment",
        "xr_vk_reset_uniform_stream",
        "xr_vk_upload_uniform_block",
        "g_vkMapMemory(g_device, g_uniform_memory, aligned, size",
        "memcpy(mapped, data, static_cast<size_t>(size))",
        "g_uniform_cursor = aligned + size",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan uniform stream validation failed: missing {token}")

    # Serialize the exact SHOC VS/PS float-register image only after the aligned upload stream exists.
    harden_vulkan_constant_snapshot(root)

    print("[vulkan-uniforms] aligned 64 KiB host-coherent stream + fixed VS[256]/PS[256] constant snapshot installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install aligned per-frame Vulkan uniform uploads for RC6 materials.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_uniform_stream(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
