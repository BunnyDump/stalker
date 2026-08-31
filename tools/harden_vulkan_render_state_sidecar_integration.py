from __future__ import annotations

import argparse
from pathlib import Path

from harden_vulkan_render_state_cull import harden as harden_vulkan_render_state_cull
from harden_vulkan_backend_stateblock_identity import harden as harden_vulkan_backend_stateblock_identity
from harden_vulkan_backend_render_state_bridge import harden as harden_vulkan_backend_render_state_bridge
from harden_vulkan_pipeline_render_state import harden as harden_vulkan_pipeline_render_state
from harden_vulkan_dynamic_stream_association import harden as harden_vulkan_dynamic_stream_association
from harden_vulkan_dynamic_stream_ranges import harden as harden_vulkan_dynamic_stream_ranges
from harden_vulkan_spirv_descriptor_contract import harden as harden_vulkan_spirv_descriptor_contract
from harden_vulkan_spirv_texture_usage import harden as harden_vulkan_spirv_texture_usage
from harden_vulkan_missing_sidecar_diagnostics import harden as harden_vulkan_missing_sidecar_diagnostics
from validate_vulkan_dynamic_stream_association import validate as validate_vulkan_dynamic_stream_association


def harden(root: Path) -> None:
    root = root.resolve()
    harden_vulkan_render_state_cull(root)
    harden_vulkan_backend_stateblock_identity(root)
    harden_vulkan_backend_render_state_bridge(root)
    harden_vulkan_pipeline_render_state(root)
    harden_vulkan_dynamic_stream_association(root)
    harden_vulkan_dynamic_stream_ranges(root)

    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    old_decl = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout,
        VkPrimitiveTopology topology);
'''
    new_decl = '''    VkPipeline xr_vk_create_graphics_pipeline(const void* vs_data, size_t vs_size, const char* vs_entry,
        const void* ps_data, size_t ps_size, const char* ps_entry,
        const xr_vk_vertex_input_layout* vertex_layout,
        VkPrimitiveTopology topology,
        const xr_vk_render_state_snapshot* render_state);
'''
    if new_decl not in text:
        if old_decl not in text:
            raise RuntimeError("render-state sidecar integration: legacy pipeline forward declaration missing")
        text = text.replace(old_decl, new_decl, 1)

    old_sig = '''    VkPipeline xr_vk_materialize_backend_pipeline(const xr_vk_backend_pipeline_key& key,
        const xr_vk_vertex_input_layout& vertex_layout)
'''
    new_sig = '''    VkPipeline xr_vk_materialize_backend_pipeline(const xr_vk_backend_pipeline_key& key,
        const xr_vk_vertex_input_layout& vertex_layout,
        const xr_vk_render_state_snapshot* render_state)
'''
    if new_sig not in text:
        if old_sig not in text:
            raise RuntimeError("render-state sidecar integration: materializer signature missing")
        text = text.replace(old_sig, new_sig, 1)

    old_guard = '''        if (!key.vertex_shader_identity || !key.pixel_shader_identity ||
            key.render_pass_generation != g_render_pass_generation ||
            key.topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM)
            return VK_NULL_HANDLE;
'''
    new_guard = '''        if (!key.vertex_shader_identity || !key.pixel_shader_identity || !render_state ||
            !render_state->identity || key.render_state_identity != render_state->identity ||
            key.render_pass_generation != g_render_pass_generation ||
            key.topology == VK_PRIMITIVE_TOPOLOGY_MAX_ENUM)
            return VK_NULL_HANDLE;
'''
    if "key.render_state_identity != render_state->identity" not in text:
        if old_guard not in text:
            raise RuntimeError("render-state sidecar integration: materializer guard missing")
        text = text.replace(old_guard, new_guard, 1)

    old_create = '''            &pixel_spirv[0], pixel_spirv.size(), "main",
            &vertex_layout, key.topology);
'''
    new_create = '''            &pixel_spirv[0], pixel_spirv.size(), "main",
            &vertex_layout, key.topology, render_state);
'''
    if "&vertex_layout, key.topology, render_state);" not in text:
        if old_create not in text:
            raise RuntimeError("render-state sidecar integration: pipeline creation call missing")
        text = text.replace(old_create, new_create, 1)

    old_call = "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)"
    new_call = "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout, render_state)"
    if new_call not in text:
        count = text.count(old_call)
        if count != 2:
            raise RuntimeError(f"render-state sidecar integration: expected two materializer calls, found {count}")
        text = text.replace(old_call, new_call)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "XR_VK_RS_CULLMODE",
        "IDirect3DStateBlock9* state_block",
        "const xr_vk_render_state_snapshot* render_state",
        "u64 render_state_identity;",
        "key.render_state_identity = render_state->identity;",
        "xr_vk_apply_render_state_snapshot",
        "VkPrimitiveTopology topology,\n        const xr_vk_render_state_snapshot* render_state);",
        "key.render_state_identity != render_state->identity",
        "&vertex_layout, key.topology, render_state);",
        "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout, render_state)",
        "xrRender_vk_vertex_stream_upload",
        "xr_vk_dynamic_vertex_range_ready",
        "xr_vk_dynamic_index_range_ready",
        "begin > g_stream_vertex_valid_end || end < g_stream_vertex_valid_begin",
        "begin > g_stream_index_valid_end || end < g_stream_index_valid_begin",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"render-state sidecar integration validation failed: missing {token}")
    if "xr_vk_materialize_backend_pipeline(pipeline_key, vertex_layout)" in final:
        raise RuntimeError("render-state sidecar integration validation failed: state-blind materializer call remains")

    harden_vulkan_spirv_descriptor_contract(root)
    harden_vulkan_spirv_texture_usage(root)
    harden_vulkan_missing_sidecar_diagnostics(root)
    validate_vulkan_dynamic_stream_association(root)
    print("[vulkan-render-state-sidecar] canonical D3D9 state + strict SPIR-V resource types + conservative per-pipeline texture usage masks + missing-sidecar diagnostics integrated")


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate render state, stream safety, typed SPIR-V texture usage and sidecar diagnostics into Vulkan pipeline materialization.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
