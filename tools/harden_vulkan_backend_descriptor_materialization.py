from __future__ import annotations

import argparse
from pathlib import Path


UNIFORM_FRAME_CAPACITY = 64 * 1024 * 1024


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old, new, 1)


def harden(root: Path) -> None:
    source = Path(root).resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    prerequisites = (
        "xr_vk_upload_constant_snapshot",
        "xr_vk_allocate_snapshot_descriptor",
        "struct xr_vk_resolved_texture_snapshot",
        "xr_vk_resolve_texture_snapshot",
        "xr_vk_bind_material_descriptor",
        "g_material_descriptor_count",
        "g_material_descriptor_capacity",
    )
    for token in prerequisites:
        if token not in text:
            raise RuntimeError(f"Vulkan backend descriptor materialization requires {token}")

    # The legacy 64 KiB stream can hold only eight 8192-byte SHOC constant snapshots.
    # Keep the old constant as a compatibility floor for older validators, but use a
    # frame arena sized for the descriptor-set budget (8192 draws * 8192 bytes).
    capacity_marker = "    const VkDeviceSize g_uniform_capacity = 65536;\n"
    frame_capacity = f"    const VkDeviceSize g_uniform_frame_capacity = {UNIFORM_FRAME_CAPACITY};\n"
    if "g_uniform_frame_capacity" not in text:
        if capacity_marker not in text:
            raise RuntimeError("Vulkan backend descriptors: uniform capacity marker missing")
        text = text.replace(capacity_marker, capacity_marker + frame_capacity, 1)

    old_bounds = (
        "        if (aligned == ~VkDeviceSize(0) || aligned > g_uniform_capacity || "
        "size > g_uniform_capacity - aligned)\n"
        "            return false;\n"
    )
    new_bounds = (
        "        if (aligned == ~VkDeviceSize(0) || aligned > g_uniform_frame_capacity || "
        "size > g_uniform_frame_capacity - aligned)\n"
        "            return false;\n"
    )
    if new_bounds not in text:
        text = replace_once(text, old_bounds, new_bounds, "per-frame uniform arena bounds")

    old_uniform_buffer = (
        "        if (!xr_vk_create_buffer(64 * 1024, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,\n"
        "                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, "
        "g_uniform_buffer, g_uniform_memory))\n"
        "            return false;\n"
    )
    new_uniform_buffer = (
        f"        if (!xr_vk_create_buffer({UNIFORM_FRAME_CAPACITY}ull, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,\n"
        "                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, "
        "g_uniform_buffer, g_uniform_memory))\n"
        "            return false;\n"
    )
    if new_uniform_buffer not in text:
        text = replace_once(text, old_uniform_buffer, new_uniform_buffer, "per-frame uniform buffer allocation")

    # Snapshot descriptor sets are transient for one in-flight frame. Keep them separate
    # from long-lived texture/material descriptor sets and free only after the frame fence.
    state_marker = "    const u32 g_material_descriptor_capacity = 8192;\n"
    frame_state = "    xr_vector<VkDescriptorSet> g_frame_descriptor_sets;\n"
    if frame_state not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan backend descriptors: descriptor capacity state marker missing")
        text = text.replace(state_marker, state_marker + frame_state, 1)

    snapshot_update = "        g_vkUpdateDescriptorSets(g_device, write_count, writes, 0, NULL);\n        return true;\n"
    snapshot_track = (
        "        g_vkUpdateDescriptorSets(g_device, write_count, writes, 0, NULL);\n"
        "        g_frame_descriptor_sets.push_back(descriptor_set);\n"
        "        return true;\n"
    )
    snapshot_start = text.find("bool xr_vk_allocate_snapshot_descriptor")
    snapshot_end = text.find("void xr_vk_free_material_descriptor", snapshot_start)
    if snapshot_start < 0 or snapshot_end < 0:
        raise RuntimeError("Vulkan backend descriptors: snapshot descriptor helper range missing")
    snapshot = text[snapshot_start:snapshot_end]
    if "g_frame_descriptor_sets.push_back(descriptor_set);" not in snapshot:
        if snapshot_update not in snapshot:
            raise RuntimeError("Vulkan backend descriptors: snapshot update marker missing")
        snapshot = snapshot.replace(snapshot_update, snapshot_track, 1)
        text = text[:snapshot_start] + snapshot + text[snapshot_end:]

    release_marker = "    bool xr_vk_bind_material_descriptor(VkCommandBuffer command_buffer, VkDescriptorSet descriptor_set)\n"
    release_helper = r'''    bool xr_vk_release_frame_descriptors()
    {
        if (g_frame_descriptor_sets.empty())
            return true;
        if (g_device == VK_NULL_HANDLE || g_descriptor_pool == VK_NULL_HANDLE || !g_vkFreeDescriptorSets)
            return false;

        const u32 count = static_cast<u32>(g_frame_descriptor_sets.size());
        if (g_vkFreeDescriptorSets(g_device, g_descriptor_pool, count, &g_frame_descriptor_sets[0]) != VK_SUCCESS)
            return false;
        g_frame_descriptor_sets.clear();
        g_material_descriptor_count = g_material_descriptor_count >= count ?
            g_material_descriptor_count - count : 0;
        return true;
    }

'''
    if "bool xr_vk_release_frame_descriptors()" not in text:
        if release_marker not in text:
            raise RuntimeError("Vulkan backend descriptors: material bind helper marker missing")
        text = text.replace(release_marker, release_helper + release_marker, 1)

    frame_reset_marker = (
        "    // One frame is in flight. Once the fence is signalled, previous uniform ranges are no longer in use.\n"
        "    xr_vk_reset_uniform_stream();\n"
    )
    frame_reset_replacement = (
        "    // One frame is in flight. Once the fence is signalled, transient descriptor sets and\n"
        "    // their uniform ranges are no longer referenced by submitted GPU work.\n"
        "    if (!xr_vk_release_frame_descriptors())\n"
        "        return false;\n"
        "    xr_vk_reset_uniform_stream();\n"
    )
    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    if frame_start < 0:
        raise RuntimeError("Vulkan backend descriptors: frame function missing")
    if "xr_vk_release_frame_descriptors()" not in text[frame_start:]:
        frame_text = text[frame_start:]
        if frame_reset_marker not in frame_text:
            raise RuntimeError("Vulkan backend descriptors: fence-safe uniform reset marker missing")
        frame_text = frame_text.replace(frame_reset_marker, frame_reset_replacement, 1)
        text = text[:frame_start] + frame_text

    count_reset = "        g_material_descriptor_count = 0;\n"
    if "        g_frame_descriptor_sets.clear();\n" not in text:
        if count_reset not in text:
            raise RuntimeError("Vulkan backend descriptors: descriptor-count teardown marker missing")
        text = text.replace(count_reset, count_reset + "        g_frame_descriptor_sets.clear();\n", 1)

    gate_signature_old = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count)\n"
        "    {\n"
    )
    gate_signature_new = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count, VkDescriptorSet& descriptor_set)\n"
        "    {\n"
        "        descriptor_set = VK_NULL_HANDLE;\n"
    )
    if gate_signature_new not in text:
        text = replace_once(text, gate_signature_old, gate_signature_new, "descriptor-producing resource gate signature")

    fail_closed_tail = r'''        // Production Vulkan draws must not bypass SHOC's active textures/constants.
        // This gate is deliberately fail-closed until the CBackend resource snapshot is
        // mirrored into Vulkan descriptors/uniforms for the exact current draw.
        return false;
'''
    materialized_tail = r'''        VkDeviceSize uniform_offset = 0;
        VkDeviceSize uniform_range = 0;
        if (!xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range))
            return false;
        if (!xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range,
                resolved_textures.pixel, resolved_textures.vertex, g_default_sampler, descriptor_set))
            return false;
        return descriptor_set != VK_NULL_HANDLE;
'''
    gate_start = text.find("bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants")
    gate_end = text.find("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    if gate_start < 0 or gate_end < 0:
        raise RuntimeError("Vulkan backend descriptors: resource gate range missing")
    gate = text[gate_start:gate_end]
    if materialized_tail not in gate:
        if fail_closed_tail not in gate:
            raise RuntimeError("Vulkan backend descriptors: fail-closed gate tail missing")
        gate = gate.replace(fail_closed_tail, materialized_tail, 1)
        text = text[:gate_start] + gate + text[gate_end:]

    # Thread the descriptor set through dynamic helpers.
    dynamic_indexed_sig_old = (
        "    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n"
    )
    dynamic_indexed_sig_new = (
        "    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n"
    )
    if dynamic_indexed_sig_new not in text:
        text = replace_once(text, dynamic_indexed_sig_old, dynamic_indexed_sig_new, "dynamic indexed descriptor ABI")

    dynamic_plain_sig_old = (
        "    bool xr_vk_record_dynamic_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n"
    )
    dynamic_plain_sig_new = (
        "    bool xr_vk_record_dynamic_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n"
    )
    if dynamic_plain_sig_new not in text:
        text = replace_once(text, dynamic_plain_sig_old, dynamic_plain_sig_new, "dynamic plain descriptor ABI")

    dynamic_indexed_guard_old = "        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_buffer ||\n"
    dynamic_indexed_guard_new = "        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE || !vertex_buffer ||\n"
    dynamic_start = text.find("bool xr_vk_record_dynamic_indexed_backend_draw")
    dynamic_plain_start = text.find("bool xr_vk_record_dynamic_backend_draw", dynamic_start)
    dynamic_indexed = text[dynamic_start:dynamic_plain_start]
    if dynamic_indexed_guard_new not in dynamic_indexed:
        if dynamic_indexed_guard_old not in dynamic_indexed:
            raise RuntimeError("Vulkan backend descriptors: dynamic indexed guard marker missing")
        dynamic_indexed = dynamic_indexed.replace(dynamic_indexed_guard_old, dynamic_indexed_guard_new, 1)
        text = text[:dynamic_start] + dynamic_indexed + text[dynamic_plain_start:]

    maker_old = "xr_vk_make_indexed_draw_packet(pipeline, D3DFMT_INDEX16, primitive, start_index,"
    maker_new = "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive, start_index,"
    if maker_new not in text:
        text = replace_once(text, maker_old, maker_new, "dynamic indexed descriptor packet")

    dynamic_plain_start = text.find("bool xr_vk_record_dynamic_backend_draw")
    dynamic_plain_end = text.find("extern \"C\" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed", dynamic_plain_start)
    dynamic_plain = text[dynamic_plain_start:dynamic_plain_end]
    plain_guard_old = "        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_buffer ||\n"
    plain_guard_new = "        if (command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE || !vertex_buffer ||\n"
    if plain_guard_new not in dynamic_plain:
        if plain_guard_old not in dynamic_plain:
            raise RuntimeError("Vulkan backend descriptors: dynamic plain guard marker missing")
        dynamic_plain = dynamic_plain.replace(plain_guard_old, plain_guard_new, 1)
    plain_draw_old = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);\n"
    )
    plain_draw_new = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        if (!xr_vk_bind_material_descriptor(command_buffer, descriptor_set))\n"
        "            return false;\n"
        "        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);\n"
    )
    if plain_draw_new not in dynamic_plain:
        if plain_draw_old not in dynamic_plain:
            raise RuntimeError("Vulkan backend descriptors: dynamic plain bind/draw marker missing")
        dynamic_plain = dynamic_plain.replace(plain_draw_old, plain_draw_new, 1)
    text = text[:dynamic_plain_start] + dynamic_plain + text[dynamic_plain_end:]

    # Thread the same descriptor set through static level/model helpers.
    static_indexed_sig_old = (
        "    bool xr_vk_record_static_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n"
    )
    static_indexed_sig_new = (
        "    bool xr_vk_record_static_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n"
    )
    if static_indexed_sig_new not in text:
        text = replace_once(text, static_indexed_sig_old, static_indexed_sig_new, "static indexed descriptor ABI")

    static_plain_sig_old = (
        "    bool xr_vk_record_static_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n"
    )
    static_plain_sig_new = (
        "    bool xr_vk_record_static_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
        "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n"
    )
    if static_plain_sig_new not in text:
        text = replace_once(text, static_plain_sig_old, static_plain_sig_new, "static plain descriptor ABI")

    static_indexed_start = text.find("bool xr_vk_record_static_indexed_backend_draw")
    static_plain_start = text.find("bool xr_vk_record_static_backend_draw", static_indexed_start)
    static_indexed = text[static_indexed_start:static_plain_start]
    if "descriptor_set == VK_NULL_HANDLE" not in static_indexed:
        static_guard_old = "        if (!vb || !ib || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_stride ||\n"
        static_guard_new = "        if (!vb || !ib || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE || !vertex_stride ||\n"
        if static_guard_old not in static_indexed:
            raise RuntimeError("Vulkan backend descriptors: static indexed guard marker missing")
        static_indexed = static_indexed.replace(static_guard_old, static_guard_new, 1)
    static_indexed_draw_old = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        g_vkCmdDrawIndexed(command_buffer, index_count, 1, 0, static_cast<s32>(base_vertex), 0);\n"
    )
    static_indexed_draw_new = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        if (!xr_vk_bind_material_descriptor(command_buffer, descriptor_set))\n"
        "            return false;\n"
        "        g_vkCmdDrawIndexed(command_buffer, index_count, 1, 0, static_cast<s32>(base_vertex), 0);\n"
    )
    if static_indexed_draw_new not in static_indexed:
        if static_indexed_draw_old not in static_indexed:
            raise RuntimeError("Vulkan backend descriptors: static indexed bind/draw marker missing")
        static_indexed = static_indexed.replace(static_indexed_draw_old, static_indexed_draw_new, 1)
        text = text[:static_indexed_start] + static_indexed + text[static_plain_start:]

    static_plain_start = text.find("bool xr_vk_record_static_backend_draw")
    static_plain_end = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer', static_plain_start)
    if static_plain_end < 0:
        static_plain_end = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed', static_plain_start)
    static_plain = text[static_plain_start:static_plain_end]
    if "descriptor_set == VK_NULL_HANDLE" not in static_plain:
        static_plain_guard_old = "        if (!vb || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_stride ||\n"
        static_plain_guard_new = "        if (!vb || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE || !vertex_stride ||\n"
        if static_plain_guard_old not in static_plain:
            raise RuntimeError("Vulkan backend descriptors: static plain guard marker missing")
        static_plain = static_plain.replace(static_plain_guard_old, static_plain_guard_new, 1)
    static_plain_draw_old = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);\n"
    )
    static_plain_draw_new = (
        "        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);\n"
        "        if (!xr_vk_bind_material_descriptor(command_buffer, descriptor_set))\n"
        "            return false;\n"
        "        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);\n"
    )
    if static_plain_draw_new not in static_plain:
        if static_plain_draw_old not in static_plain:
            raise RuntimeError("Vulkan backend descriptors: static plain bind/draw marker missing")
        static_plain = static_plain.replace(static_plain_draw_old, static_plain_draw_new, 1)
    text = text[:static_plain_start] + static_plain + text[static_plain_end:]

    # Materialize once per exported draw, then reuse the same descriptor for dynamic or
    # static geometry. If materialization fails, the established D3D9 fallback remains.
    indexed_gate_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    indexed_gate_new = (
        "    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;\n"
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count, descriptor_set) &&\n"
        "        xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if indexed_gate_new not in text:
        text = replace_once(text, indexed_gate_old, indexed_gate_new, "indexed export descriptor materialization")

    indexed_static_gate_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    indexed_static_gate_new = (
        "    if (descriptor_set != VK_NULL_HANDLE &&\n"
        "        xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if indexed_static_gate_new not in text:
        text = replace_once(text, indexed_static_gate_old, indexed_static_gate_new, "indexed static descriptor reuse")

    plain_gate_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    plain_gate_new = (
        "    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;\n"
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count, descriptor_set) &&\n"
        "        xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if plain_gate_new not in text:
        text = replace_once(text, plain_gate_old, plain_gate_new, "plain export descriptor materialization")

    plain_static_gate_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    plain_static_gate_new = (
        "    if (descriptor_set != VK_NULL_HANDLE &&\n"
        "        xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if plain_static_gate_new not in text:
        text = replace_once(text, plain_static_gate_old, plain_static_gate_new, "plain static descriptor reuse")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        f"const VkDeviceSize g_uniform_frame_capacity = {UNIFORM_FRAME_CAPACITY}",
        f"xr_vk_create_buffer({UNIFORM_FRAME_CAPACITY}ull, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT",
        "g_frame_descriptor_sets.push_back(descriptor_set)",
        "bool xr_vk_release_frame_descriptors()",
        "g_vkFreeDescriptorSets(g_device, g_descriptor_pool, count, &g_frame_descriptor_sets[0])",
        "if (!xr_vk_release_frame_descriptors())",
        "VkDescriptorSet& descriptor_set",
        "xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range)",
        "xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range",
        "return descriptor_set != VK_NULL_HANDLE;",
        "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive",
        "xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend descriptor materialization validation failed: missing {token}")

    if fail_closed_tail in final:
        raise RuntimeError("Vulkan backend descriptor materialization validation failed: production resource gate remains closed")

    print("[vulkan-backend-descriptors] exact SHOC constant snapshot + resolved PS[16]/VS[5] textures now materialize one fence-safe descriptor set per live Vulkan draw")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the RC6 Vulkan production resource gate with exact per-draw SHOC descriptors.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
