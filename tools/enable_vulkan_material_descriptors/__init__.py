from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_legacy_module():
    legacy_path = Path(__file__).resolve().parent.parent / "enable_vulkan_material_descriptors.py"
    spec = importlib.util.spec_from_file_location("_xr_vk_material_descriptors_legacy", legacy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load legacy material descriptor installer: {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_material_descriptors(root: Path) -> None:
    """Run the existing descriptor installer without dropping the topology-aware packet ABI.

    The indexed-draw layer gained D3DPRIMITIVETYPE in the packet factory, while the legacy
    material-descriptor installer still matches the older signature.  Present the legacy
    marker only while it performs its established descriptor edits, then restore the
    topology argument in the descriptor-aware signature before any later hardener runs.
    """
    root = Path(root).resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    topology_signature = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, D3DFORMAT index_format,
        D3DPRIMITIVETYPE primitive_type, u32 start_index, u32 primitive_count, s32 base_vertex,
        VkDeviceSize vertex_offset, VkDeviceSize index_stream_offset, xr_vk_indexed_draw_packet& draw)
'''
    legacy_signature = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, D3DFORMAT index_format,
        u32 start_index, u32 primitive_count, s32 base_vertex, VkDeviceSize vertex_offset,
        VkDeviceSize index_stream_offset, xr_vk_indexed_draw_packet& draw)
'''
    descriptor_legacy_signature = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, VkDescriptorSet descriptor_set,
        D3DFORMAT index_format, u32 start_index, u32 primitive_count, s32 base_vertex,
        VkDeviceSize vertex_offset, VkDeviceSize index_stream_offset, xr_vk_indexed_draw_packet& draw)
'''
    descriptor_topology_signature = '''    bool xr_vk_make_indexed_draw_packet(VkPipeline pipeline, VkDescriptorSet descriptor_set,
        D3DFORMAT index_format, D3DPRIMITIVETYPE primitive_type, u32 start_index, u32 primitive_count,
        s32 base_vertex, VkDeviceSize vertex_offset, VkDeviceSize index_stream_offset,
        xr_vk_indexed_draw_packet& draw)
'''

    text = source.read_text(encoding="utf-8")
    if descriptor_topology_signature in text:
        final = text
    else:
        if topology_signature in text:
            source.write_text(text.replace(topology_signature, legacy_signature, 1), encoding="utf-8")
        elif legacy_signature not in text and descriptor_legacy_signature not in text:
            raise RuntimeError("Topology-aware material descriptors: indexed packet factory marker missing")

        legacy = _load_legacy_module()
        legacy.install_material_descriptors(root)

        final = source.read_text(encoding="utf-8")
        if descriptor_legacy_signature not in final:
            raise RuntimeError("Topology-aware material descriptors: legacy descriptor signature was not materialized")
        final = final.replace(descriptor_legacy_signature, descriptor_topology_signature, 1)
        source.write_text(final, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        descriptor_topology_signature,
        "draw.primitive_type = primitive_type;",
        "draw.descriptor_set = descriptor_set;",
        "pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE",
        "xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Topology-aware material descriptor validation failed: missing {token}")

    if legacy_signature in final or descriptor_legacy_signature in final:
        raise RuntimeError("Topology-aware material descriptor validation failed: stale packet ABI remains")

    print("[vulkan-materials-v2] descriptor-aware indexed packet factory preserves D3D primitive topology")
