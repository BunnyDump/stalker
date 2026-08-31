from __future__ import annotations

import argparse
from pathlib import Path

from validate_vulkan_descriptor_snapshot_schema import validate as validate_vulkan_descriptor_snapshot_schema


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    required = (
        "VkDeviceSize g_uniform_cursor",
        "const VkDeviceSize g_uniform_capacity = 65536",
        "xr_vk_align_uniform_offset",
        "minUniformBufferOffsetAlignment",
        "xr_vk_upload_uniform_block",
        "g_vkMapMemory(g_device, g_uniform_memory, aligned, size",
        "memcpy(mapped, data, static_cast<size_t>(size))",
        "xr_vk_reset_uniform_stream();",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan uniform stream validation failed: missing {token}")

    frame = text.find("bool xr_vk_bootstrap_frame()")
    wait = text.find("g_vkWaitForFences", frame)
    reset = text.find("xr_vk_reset_uniform_stream();", frame)
    acquire = text.find("g_vkAcquireNextImageKHR", frame)
    if min(frame, wait, reset, acquire) < 0 or not (frame < wait < reset < acquire):
        raise RuntimeError("Vulkan uniform stream validation failed: per-frame reset is not fence-safe")

    validate_vulkan_descriptor_snapshot_schema(root)

    print("[validate-vulkan-uniforms] aligned upload path, fence-safe reset, 8192-byte constant snapshot and UBO+PS[16]+VS[5] descriptor ABI verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
