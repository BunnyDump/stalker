from __future__ import annotations

import argparse
from pathlib import Path

from enable_vulkan_device_selection import enable_device_selection
from enable_vulkan_runtime_stack import install_runtime_stack
from validate_vulkan_extensions import install_extension_validation
from enable_vulkan_render_core import install_render_core
from enable_vulkan_pipeline import install_pipeline
from enable_vulkan_renderpass_frame import install_renderpass_frame
from enable_vulkan_dynamic_state import install_dynamic_state
from enable_vulkan_draw_commands import install_draw_commands
from enable_vulkan_geometry_bridge import install_geometry_bridge
from enable_vulkan_sgeometry_adapter import install_sgeometry_adapter
from enable_vulkan_stream_mirror import install_stream_mirror
from enable_vulkan_indexed_draw import install_indexed_draw
from validate_vulkan_frame_path import validate as validate_vulkan_frame_path
from validate_vulkan_geometry_bridge import validate as validate_vulkan_geometry_bridge

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
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
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
    install_extension_validation(root)
    install_render_core(root)
    install_pipeline(root)
    install_renderpass_frame(root)
    install_dynamic_state(root)
    install_draw_commands(root)
    install_geometry_bridge(root)
    install_sgeometry_adapter(root)
    install_stream_mirror(root)
    install_indexed_draw(root)
    validate_vulkan_frame_path(root)
    validate_vulkan_geometry_bridge(root)
    print("[vulkan-capability] lifecycle-safe probe + native runtime + extension validation + render core + SPIR-V pipeline + render-pass frame + dynamic state + draw entry points + D3D9 geometry bridge + native SGeometry/topology adapter + dynamic vertex/index stream mirrors + indexed draw packets verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make the Vulkan capability probe independent from the active renderer lifecycle.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())