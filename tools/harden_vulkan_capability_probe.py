from __future__ import annotations

import argparse
from pathlib import Path

from enable_vulkan_device_selection import enable_device_selection
from enable_vulkan_runtime_stack import install_runtime_stack
from enable_vulkan_render_infra import enable_render_infrastructure
from enable_vulkan_native_loader import enable_native_loader

PROBE_DECL = "bool xr_vk_bootstrap_probe();\n"
PROBE_IMPL = r'''
bool xr_vk_bootstrap_probe()
{
    const bool was_initialized = g_vulkan_instance != VK_NULL_HANDLE;
    if (!xr_vk_bootstrap_initialize())
        return false;

    const bool available = g_physical_device_count > 0;
    if (!was_initialized)
        xr_vk_bootstrap_shutdown();
    return available;
}

'''
TEST_HW_SOURCE = r'''#include "stdafx.h"
#include "vk_bootstrap.h"

BOOL xrRender_test_hw()
{
    return xr_vk_bootstrap_probe() ? TRUE : FALSE;
}
'''


def harden(root: Path) -> None:
    root = root.resolve()
    renderer = root / "xr_3da" / "xrRender_VK"
    header = renderer / "vk_bootstrap.h"
    source = renderer / "vk_bootstrap.cpp"
    test_hw = renderer / "r2_test_hw.cpp"
    for path in (header, source, test_hw):
        if not path.is_file():
            raise FileNotFoundError(path)

    header_text = header.read_text(encoding="utf-8")
    if PROBE_DECL not in header_text:
        marker = "unsigned xr_vk_bootstrap_physical_device_count();\n"
        if marker not in header_text:
            raise RuntimeError("Vulkan probe hardening: bootstrap declaration marker not found")
        header_text = header_text.replace(marker, marker + PROBE_DECL, 1)
        header.write_text(header_text, encoding="utf-8")

    source_text = source.read_text(encoding="utf-8")
    if "bool xr_vk_bootstrap_probe()" not in source_text:
        marker = "unsigned xr_vk_bootstrap_physical_device_count()\n"
        if marker not in source_text:
            raise RuntimeError("Vulkan probe hardening: bootstrap implementation marker not found")
        source_text = source_text.replace(marker, PROBE_IMPL + marker, 1)
        source.write_text(source_text, encoding="utf-8")

    test_hw.write_text(TEST_HW_SOURCE, encoding="utf-8")

    final_source = source.read_text(encoding="utf-8")
    for token in ("was_initialized", "xr_vk_bootstrap_probe()", "if (!was_initialized)"):
        if token not in final_source:
            raise RuntimeError(f"Vulkan probe hardening validation failed: missing {token}")
    if "xr_vk_bootstrap_shutdown()" in test_hw.read_text(encoding="utf-8"):
        raise RuntimeError("Vulkan probe hardening validation failed: hardware probe owns runtime shutdown")

    enable_device_selection(root)
    install_runtime_stack(root)
    enable_render_infrastructure(root)
    enable_native_loader(root)
    print("[vulkan-capability] native Vulkan runtime/render infrastructure installed without DXVK bridge or DllMain probing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make the Vulkan capability probe independent from the active renderer lifecycle.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
