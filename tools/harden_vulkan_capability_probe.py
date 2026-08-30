from __future__ import annotations

import argparse
from pathlib import Path

from enable_vulkan_device_selection import enable_device_selection
from enable_vulkan_runtime_stack import install_runtime_stack
from validate_vulkan_extensions import install_extension_validation
from enable_vulkan_render_core import install_render_core
from harden_vulkan_upload_capacity import harden as harden_vulkan_upload_capacity
from enable_vulkan_pipeline import install_pipeline
from enable_vulkan_renderpass_frame import install_renderpass_frame
from enable_vulkan_dynamic_state import install_dynamic_state
from enable_vulkan_draw_commands import install_draw_commands
from enable_vulkan_geometry_bridge import install_geometry_bridge
from harden_vulkan_pipeline_topology import harden as harden_vulkan_pipeline_topology
from enable_vulkan_sgeometry_adapter import install_sgeometry_adapter
from enable_vulkan_stream_mirror import install_stream_mirror
from harden_vulkan_stream_lifetime import harden as harden_vulkan_stream_lifetime
from validate_vulkan_stream_lifetime import validate as validate_vulkan_stream_lifetime
from enable_vulkan_indexed_draw import install_indexed_draw
from harden_vulkan_render_state_snapshot import harden as harden_vulkan_render_state_snapshot
from enable_vulkan_backend_dispatch import install_backend_dispatch
from harden_vulkan_backend_shader_identity import harden as harden_vulkan_backend_shader_identity
from validate_vulkan_backend_dispatch import validate as validate_vulkan_backend_dispatch
from enable_vulkan_material_descriptors import install_material_descriptors
from harden_vulkan_descriptor_capacity import harden as harden_vulkan_descriptor_capacity
from enable_vulkan_texture_bridge import install_texture_bridge
from harden_vulkan_texture_copy import harden as harden_vulkan_texture_copy
from harden_vulkan_frame_fence import harden as harden_vulkan_frame_fence
from harden_vulkan_texture_lifetime import harden as harden_vulkan_texture_lifetime
from harden_vulkan_present_state import harden as harden_vulkan_present_state
from harden_vulkan_swapchain_recreation import harden as harden_vulkan_swapchain_recreation
from enable_vulkan_uniform_stream import install_uniform_stream
from harden_vulkan_resource_lifetimes import harden as harden_vulkan_resource_lifetimes
from harden_vulkan_transactional_swapchain import harden as harden_vulkan_transactional_swapchain
from harden_vulkan_swapchain_format_continuity import harden as harden_vulkan_swapchain_format_continuity
from harden_vulkan_swapchain_retirement_boundary import harden as harden_vulkan_swapchain_retirement_boundary
from harden_vulkan_pipeline_generation import harden as harden_vulkan_pipeline_generation
from harden_vulkan_frame_recording_lifecycle import harden as harden_vulkan_frame_recording_lifecycle
from harden_vulkan_backend_active_frame import harden as harden_vulkan_backend_active_frame
from harden_vulkan_shader_bytecode_identity import harden as harden_vulkan_shader_bytecode_identity
from harden_vulkan_backend_pipeline_registry import harden as harden_vulkan_backend_pipeline_registry
from harden_vulkan_backend_pipeline_key_semantics import harden as harden_vulkan_backend_pipeline_key_semantics
from enable_vulkan_shader_sidecar_loader import install as install_vulkan_shader_sidecar_loader
from validate_vulkan_pipeline_generation import validate as validate_vulkan_pipeline_generation
from validate_vulkan_frame_path import validate as validate_vulkan_frame_path
from validate_vulkan_geometry_bridge import validate as validate_vulkan_geometry_bridge
from validate_vulkan_indexed_draw import validate as validate_vulkan_indexed_draw
from validate_vulkan_material_descriptors import validate as validate_vulkan_material_descriptors
from validate_vulkan_texture_bridge import validate as validate_vulkan_texture_bridge
from validate_vulkan_uniform_stream import validate as validate_vulkan_uniform_stream

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
    harden_vulkan_upload_capacity(root)
    install_pipeline(root)
    install_renderpass_frame(root)
    install_dynamic_state(root)
    install_draw_commands(root)
    install_geometry_bridge(root)
    install_sgeometry_adapter(root)
    harden_vulkan_pipeline_topology(root)
    install_stream_mirror(root)
    harden_vulkan_stream_lifetime(root)
    install_indexed_draw(root)
    harden_vulkan_render_state_snapshot(root)
    install_backend_dispatch(root)
    harden_vulkan_backend_shader_identity(root)
    install_material_descriptors(root)
    harden_vulkan_descriptor_capacity(root)
    install_texture_bridge(root)
    harden_vulkan_texture_copy(root)
    harden_vulkan_frame_fence(root)
    harden_vulkan_texture_lifetime(root)
    harden_vulkan_present_state(root)
    harden_vulkan_swapchain_recreation(root)
    install_uniform_stream(root)
    harden_vulkan_resource_lifetimes(root)
    harden_vulkan_transactional_swapchain(root)
    harden_vulkan_swapchain_format_continuity(root)
    harden_vulkan_swapchain_retirement_boundary(root)
    harden_vulkan_pipeline_generation(root)
    harden_vulkan_frame_recording_lifecycle(root)
    harden_vulkan_backend_active_frame(root)
    harden_vulkan_shader_bytecode_identity(root)
    harden_vulkan_backend_pipeline_registry(root)
    harden_vulkan_backend_pipeline_key_semantics(root)
    install_vulkan_shader_sidecar_loader(root)
    validate_vulkan_frame_path(root)
    validate_vulkan_geometry_bridge(root)
    validate_vulkan_stream_lifetime(root)
    validate_vulkan_indexed_draw(root)
    validate_vulkan_backend_dispatch(root)
    validate_vulkan_material_descriptors(root)
    validate_vulkan_texture_bridge(root)
    validate_vulkan_uniform_stream(root)
    validate_vulkan_pipeline_generation(root)
    print("[vulkan-capability] lifecycle-safe probe + native runtime + extension validation + render core + 64 MiB upload staging + SPIR-V pipeline + topology-aware graphics pipeline factory + R2 Render-scoped begin/end render-pass recording + active command buffer + backend active-frame gating + canonical D3D9 depth/blend/color-write state snapshots + D3D9 bytecode-stable VS/PS identity + semantic declaration/stride/topology/render-pass keyed backend pipeline registry + bytecode-keyed validated SPIR-V sidecar materialization + dynamic state + draw entry points + D3D9 geometry bridge + native SGeometry/topology adapter + fence-safe dynamic vertex/index stream mirrors + topology-correct indexed draw packets + live CBackend renderer dispatch with release-safe VS/PS identity and fail-closed D3D fallback + 8192-set descriptor capacity + persistent material/device resources across resize + exact oldSwapchain retirement boundary + clean recovery + swapchain format continuity + render-pass generation-owned graphics pipelines + stale draw rejection + material descriptor binding + sampled texture bridge + block-aligned BC uploads + failure-safe frame fence + deferred GPU-safe texture destruction + safe present state + resilient Win32 swapchain recreation + aligned per-frame uniform stream verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Make the Vulkan capability probe independent from the active renderer lifecycle.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
