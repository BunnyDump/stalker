from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    # Avoid 32-bit wrap before promotion in the non-indexed range check.
    old_range = "const VkDeviceSize required_vertex_bytes = static_cast<VkDeviceSize>(start_vertex + vertex_count) * vertex_stride;"
    new_range = "const VkDeviceSize required_vertex_bytes = (static_cast<VkDeviceSize>(start_vertex) + vertex_count) * vertex_stride;"
    if old_range in text:
        text = text.replace(old_range, new_range, 1)
    elif new_range not in text:
        raise RuntimeError("Vulkan static geometry lifetime: non-indexed range marker not found")

    # Static mirrors are device-owned. They must be released while the device and function table are alive.
    shutdown_marker = "    void xr_vk_destroy_window_runtime()\n    {\n        xr_vk_destroy_frame_resources();\n"
    shutdown_hardened = "    void xr_vk_destroy_window_runtime()\n    {\n        xr_vk_destroy_frame_resources();\n        xr_vk_clear_static_geometry_mirrors();\n"
    if shutdown_hardened not in text:
        if shutdown_marker not in text:
            raise RuntimeError("Vulkan static geometry lifetime: window-runtime shutdown marker not found")
        text = text.replace(shutdown_marker, shutdown_hardened, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "(static_cast<VkDeviceSize>(start_vertex) + vertex_count) * vertex_stride",
        "xr_vk_destroy_frame_resources();\n        xr_vk_clear_static_geometry_mirrors();",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan static geometry lifetime validation failed: missing {token}")

    destroy_runtime = final.find("void xr_vk_destroy_window_runtime()")
    clear_static = final.find("xr_vk_clear_static_geometry_mirrors();", destroy_runtime)
    destroy_device = final.find("g_vkDestroyDevice(g_device, NULL)", destroy_runtime)
    clear_table = final.find("xr_vk_clear_device_function_table();", destroy_runtime)
    if min(destroy_runtime, clear_static, destroy_device, clear_table) < 0 or not clear_static < destroy_device < clear_table:
        raise RuntimeError("Vulkan static geometry lifetime validation failed: static mirrors must retire before device/function table")

    print("[vulkan-static-geometry-lifetime] widened range arithmetic + device-safe static mirror retirement installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden static Vulkan geometry range arithmetic and shutdown lifetime.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
