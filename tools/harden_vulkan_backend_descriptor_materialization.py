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
    for token in (
        "xr_vk_upload_constant_snapshot",
        "xr_vk_allocate_snapshot_descriptor",
        "struct xr_vk_resolved_texture_snapshot",
        "xr_vk_resolve_texture_snapshot",
        "xr_vk_bind_material_descriptor",
        "g_material_descriptor_count",
        "g_material_descriptor_capacity",
        "bool xr_vk_bootstrap_begin_frame()",
        "bool xr_vk_bootstrap_end_frame()",
    ):
        if token not in text:
            raise RuntimeError(f"Vulkan backend descriptor materialization requires {token}")

    # One SHOC constant image is 8192 bytes. 64 KiB allowed only eight Vulkan draws;
    # size the per-frame uniform arena to the 8192 descriptor-set budget instead.
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

    allocation_old = (
        "        if (g_uniform_buffer == VK_NULL_HANDLE &&\n"
        "            !xr_vk_create_buffer(64 * 1024, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,\n"
        "                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_uniform_buffer, g_uniform_memory))\n"
        "            return false;\n"
    )
    allocation_new = (
        "        if (g_uniform_buffer == VK_NULL_HANDLE &&\n"
        f"            !xr_vk_create_buffer({UNIFORM_FRAME_CAPACITY}ull, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,\n"
        "                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_uniform_buffer, g_uniform_memory))\n"
        "            return false;\n"
    )
    if allocation_new not in text:
        text = replace_once(text, allocation_old, allocation_new, "persistent per-frame uniform buffer allocation")

    state_marker = "    const u32 g_material_descriptor_capacity = 8192;\n"
    if "    xr_vector<VkDescriptorSet> g_frame_descriptor_sets;\n" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan backend descriptors: descriptor capacity marker missing")
        text = text.replace(state_marker, state_marker + "    xr_vector<VkDescriptorSet> g_frame_descriptor_sets;\n", 1)

    # Snapshot allocations are frame-transient. Track every successfully updated set.
    snapshot_start = text.find("bool xr_vk_allocate_snapshot_descriptor")
    snapshot_end = text.find("void xr_vk_free_material_descriptor", snapshot_start)
    if snapshot_start < 0 or snapshot_end < 0:
        raise RuntimeError("Vulkan backend descriptors: snapshot helper range missing")
    snapshot = text[snapshot_start:snapshot_end]
    update = "        g_vkUpdateDescriptorSets(g_device, write_count, writes, 0, NULL);\n        return true;\n"
    tracked = (
        "        g_vkUpdateDescriptorSets(g_device, write_count, writes, 0, NULL);\n"
        "        g_frame_descriptor_sets.push_back(descriptor_set);\n"
        "        return true;\n"
    )
    if "g_frame_descriptor_sets.push_back(descriptor_set);" not in snapshot:
        if update not in snapshot:
            raise RuntimeError("Vulkan backend descriptors: snapshot update marker missing")
        snapshot = snapshot.replace(update, tracked, 1)
        text = text[:snapshot_start] + snapshot + text[snapshot_end:]

    bind_marker = "    bool xr_vk_bind_material_descriptor(VkCommandBuffer command_buffer, VkDescriptorSet descriptor_set)\n"
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
        if bind_marker not in text:
            raise RuntimeError("Vulkan backend descriptors: bind helper marker missing")
        text = text.replace(bind_marker, release_helper + bind_marker, 1)

    # Split lifecycle invariant: wait for the one in-flight fence, then retire descriptor
    # sets, then rewind the uniform arena. Never free descriptors before the fence.
    begin_start = text.find("bool xr_vk_bootstrap_begin_frame()")
    end_start = text.find("bool xr_vk_bootstrap_end_frame()", begin_start)
    begin = text[begin_start:end_start]
    reset_marker = "    xr_vk_reset_uniform_stream();\n"
    reset_new = (
        "    if (!xr_vk_release_frame_descriptors())\n"
        "        return false;\n"
        "    xr_vk_reset_uniform_stream();\n"
    )
    if "xr_vk_release_frame_descriptors()" not in begin:
        if reset_marker not in begin:
            raise RuntimeError("Vulkan backend descriptors: begin-frame uniform reset marker missing")
        begin = begin.replace(reset_marker, reset_new, 1)
        text = text[:begin_start] + begin + text[end_start:]

    # Full descriptor-pool destruction implicitly releases any remaining sets; clear only
    # the CPU tracking vector when the pool/count are reset.
    reset_count = "        g_material_descriptor_count = 0;\n"
    if "        g_frame_descriptor_sets.clear();\n" not in text:
        if reset_count not in text:
            raise RuntimeError("Vulkan backend descriptors: teardown descriptor-count reset missing")
        text = text.replace(reset_count, reset_count + "        g_frame_descriptor_sets.clear();\n", 1)

    gate_old = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count)\n"
        "    {\n"
    )
    gate_new = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count, VkDescriptorSet& descriptor_set)\n"
        "    {\n"
        "        descriptor_set = VK_NULL_HANDLE;\n"
    )
    if gate_new not in text:
        text = replace_once(text, gate_old, gate_new, "descriptor-producing resource gate")

    gate_start = text.find("bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants")
    gate_end = text.find("    bool xr_vk_record_dynamic_indexed_backend_draw", gate_start)
    gate = text[gate_start:gate_end]
    if "xr_vk_allocate_snapshot_descriptor(g_uniform_buffer" not in gate:
        tail = "        return false;\n"
        last = gate.rfind(tail)
        if last < 0:
            raise RuntimeError("Vulkan backend descriptors: fail-closed resource-gate tail missing")
        materialize = (
            "        VkDeviceSize uniform_offset = 0;\n"
            "        VkDeviceSize uniform_range = 0;\n"
            "        if (!xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range))\n"
            "            return false;\n"
            "        if (!xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range,\n"
            "                resolved_textures.pixel, resolved_textures.vertex, g_default_sampler, descriptor_set))\n"
            "            return false;\n"
            "        return descriptor_set != VK_NULL_HANDLE;\n"
        )
        gate = gate[:last] + materialize + gate[last + len(tail):]
        text = text[:gate_start] + gate + text[gate_end:]

    # Geometry recorders receive the already materialized descriptor. Indexed dynamic
    # packets carry it through xr_vk_indexed_draw_packet; non-indexed/static paths bind it
    # explicitly immediately after the graphics pipeline.
    replacements = (
        (
            "    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n",
            "    bool xr_vk_record_dynamic_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n",
            "dynamic indexed descriptor ABI",
        ),
        (
            "    bool xr_vk_record_dynamic_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n",
            "    bool xr_vk_record_dynamic_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n",
            "dynamic plain descriptor ABI",
        ),
        (
            "    bool xr_vk_record_static_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n",
            "    bool xr_vk_record_static_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,\n",
            "static indexed descriptor ABI",
        ),
        (
            "    bool xr_vk_record_static_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n",
            "    bool xr_vk_record_static_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,\n"
            "        VkDescriptorSet descriptor_set, D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,\n",
            "static plain descriptor ABI",
        ),
    )
    for old, new, label in replacements:
        if new not in text:
            text = replace_once(text, old, new, label)

    # Require descriptor presence in all four recorders.
    ranges = (
        ("bool xr_vk_record_dynamic_indexed_backend_draw", "bool xr_vk_record_dynamic_backend_draw"),
        ("bool xr_vk_record_dynamic_backend_draw", 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'),
        ("bool xr_vk_record_static_indexed_backend_draw", "bool xr_vk_record_static_backend_draw"),
        ("bool xr_vk_record_static_backend_draw", 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer'),
    )
    for start_token, end_token in ranges:
        start = text.find(start_token)
        end = text.find(end_token, start)
        if start < 0 or end < 0:
            raise RuntimeError(f"Vulkan backend descriptors: recorder range missing: {start_token}")
        block = text[start:end]
        if "descriptor_set == VK_NULL_HANDLE" not in block:
            guard = "pipeline == VK_NULL_HANDLE ||"
            if guard not in block:
                raise RuntimeError(f"Vulkan backend descriptors: pipeline guard missing: {start_token}")
            block = block.replace(guard, guard + " descriptor_set == VK_NULL_HANDLE ||", 1)
            text = text[:start] + block + text[end:]

    maker_old = "xr_vk_make_indexed_draw_packet(pipeline, VK_NULL_HANDLE, D3DFMT_INDEX16, primitive, start_index,"
    maker_older = "xr_vk_make_indexed_draw_packet(pipeline, D3DFMT_INDEX16, primitive, start_index,"
    maker_new = "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive, start_index,"
    if maker_new not in text:
        if maker_old in text:
            text = replace_once(text, maker_old, maker_new, "dynamic indexed descriptor packet")
        else:
            text = replace_once(text, maker_older, maker_new, "dynamic indexed descriptor packet")

    # Bind descriptor for three direct-draw recorders. Indexed dynamic already binds through
    # xr_vk_record_indexed_draw(draw.descriptor_set).
    for start_token, end_token, draw_token in (
        ("bool xr_vk_record_dynamic_backend_draw", 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed', "g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);"),
        ("bool xr_vk_record_static_indexed_backend_draw", "bool xr_vk_record_static_backend_draw", "g_vkCmdDrawIndexed(command_buffer, index_count, 1, 0, static_cast<s32>(base_vertex), 0);"),
        ("bool xr_vk_record_static_backend_draw", 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer', "g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);"),
    ):
        start = text.find(start_token)
        end = text.find(end_token, start)
        block = text[start:end]
        if "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)" not in block:
            marker = "        " + draw_token + "\n"
            bind = (
                "        if (!xr_vk_bind_material_descriptor(command_buffer, descriptor_set))\n"
                "            return false;\n" + marker
            )
            if marker not in block:
                raise RuntimeError(f"Vulkan backend descriptors: draw marker missing: {start_token}")
            block = block.replace(marker, bind, 1)
            text = text[:start] + block + text[end:]

    # Exports materialize one set and reuse it for dynamic/static geometry fallback.
    indexed_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    indexed_new = (
        "    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;\n"
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count, descriptor_set) &&\n"
        "        xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if indexed_new not in text:
        text = replace_once(text, indexed_old, indexed_new, "indexed export descriptor materialization")

    indexed_static_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    indexed_static_new = (
        "    if (descriptor_set != VK_NULL_HANDLE &&\n"
        "        xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if indexed_static_new not in text:
        text = replace_once(text, indexed_static_old, indexed_static_new, "indexed static descriptor reuse")

    plain_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    plain_new = (
        "    VkDescriptorSet descriptor_set = VK_NULL_HANDLE;\n"
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count, descriptor_set) &&\n"
        "        xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if plain_new not in text:
        text = replace_once(text, plain_old, plain_new, "plain export descriptor materialization")

    plain_static_old = (
        "    if (xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive,\n"
    )
    plain_static_new = (
        "    if (descriptor_set != VK_NULL_HANDLE &&\n"
        "        xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive,\n"
    )
    if plain_static_new not in text:
        text = replace_once(text, plain_static_old, plain_static_new, "plain static descriptor reuse")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        f"const VkDeviceSize g_uniform_frame_capacity = {UNIFORM_FRAME_CAPACITY}",
        f"xr_vk_create_buffer({UNIFORM_FRAME_CAPACITY}ull, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT",
        "g_frame_descriptor_sets.push_back(descriptor_set)",
        "bool xr_vk_release_frame_descriptors()",
        "g_vkFreeDescriptorSets(g_device, g_descriptor_pool, count, &g_frame_descriptor_sets[0])",
        "VkDescriptorSet& descriptor_set",
        "xr_vk_upload_constant_snapshot(vertex_constants, pixel_constants, uniform_offset, uniform_range)",
        "xr_vk_allocate_snapshot_descriptor(g_uniform_buffer, uniform_offset, uniform_range",
        "return descriptor_set != VK_NULL_HANDLE;",
        "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive",
        "xr_vk_record_dynamic_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_dynamic_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend descriptor materialization validation failed: missing {token}")

    begin_start = final.index("bool xr_vk_bootstrap_begin_frame()")
    end_start = final.index("bool xr_vk_bootstrap_end_frame()", begin_start)
    begin = final[begin_start:end_start]
    wait = begin.index("g_vkWaitForFences")
    release = begin.index("xr_vk_release_frame_descriptors()", wait)
    reset = begin.index("xr_vk_reset_uniform_stream()", release)
    if not wait < release < reset:
        raise RuntimeError("Vulkan backend descriptor materialization validation failed: descriptor retirement is not fence-safe")

    print("[vulkan-backend-descriptors] per-draw SHOC UBO + PS[16] + VS[5] descriptors materialized for dynamic/static indexed/non-indexed Vulkan draws; transient sets retire after the in-flight frame fence")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the RC6 Vulkan production resource gate with exact per-draw SHOC descriptors.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
