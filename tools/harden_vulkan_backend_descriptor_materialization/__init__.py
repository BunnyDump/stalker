from __future__ import annotations

import importlib.util
from pathlib import Path


_STATIC_SENTINEL = '// extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer // descriptor-boundary sentinel\n'
_BACKEND_EXPORT = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'
_STATIC_PLAIN = "bool xr_vk_record_static_backend_draw"


def _load_impl():
    impl_path = Path(__file__).resolve().parent.parent / "harden_vulkan_backend_descriptor_materialization.py"
    spec = importlib.util.spec_from_file_location("_xr_vk_backend_descriptor_materialization_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Vulkan descriptor materialization implementation: {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def harden(root: Path) -> None:
    root = Path(root).resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if "xr_vk_find_pipeline_texture_usage" not in text:
        raise RuntimeError("Vulkan descriptor materialization requires SPIR-V per-pipeline texture usage masks")

    static_plain = text.find(_STATIC_PLAIN)
    backend_export = text.find(_BACKEND_EXPORT, static_plain)
    register_after_static = text.find(
        'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer',
        static_plain,
    )
    if static_plain < 0 or backend_export < 0:
        raise RuntimeError("Vulkan descriptor materialization bridge: static/backend recorder markers missing")
    if register_after_static < 0 and _STATIC_SENTINEL not in text:
        text = text[:backend_export] + _STATIC_SENTINEL + text[backend_export:]
        source.write_text(text, encoding="utf-8")

    impl = _load_impl()
    try:
        impl.harden(root)
    finally:
        final = source.read_text(encoding="utf-8")
        if _STATIC_SENTINEL in final:
            source.write_text(final.replace(_STATIC_SENTINEL, "", 1), encoding="utf-8")

    final = source.read_text(encoding="utf-8")

    gate_old = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count, VkDescriptorSet& descriptor_set)\n"
    )
    gate_new = (
        "    bool xr_vk_backend_draw_resources_ready(VkPipeline pipeline, const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count, VkDescriptorSet& descriptor_set)\n"
    )
    if gate_new not in final:
        if gate_old not in final:
            raise RuntimeError("Vulkan descriptor materialization bridge: resource gate signature missing")
        final = final.replace(gate_old, gate_new, 1)

    call_old = "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,"
    call_new = "xr_vk_backend_draw_resources_ready(pipeline, vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,"
    if call_new not in final:
        count = final.count(call_old)
        if count != 2:
            raise RuntimeError(f"Vulkan descriptor materialization bridge: expected two resource-gate calls, found {count}")
        final = final.replace(call_old, call_new)

    full_sparse_guard = (
        "        for (u32 i = 0; i < XR_VK_PIXEL_TEXTURE_SLOTS; ++i)\n"
        "            if (!resolved_textures.pixel[i])\n"
        "                return false;\n"
        "        for (u32 i = 0; i < XR_VK_VERTEX_TEXTURE_SLOTS; ++i)\n"
        "            if (!resolved_textures.vertex[i])\n"
        "                return false;\n"
    )
    usage_guard = (
        "        u32 pixel_usage_mask = 0;\n"
        "        u32 vertex_usage_mask = 0;\n"
        "        if (!xr_vk_find_pipeline_texture_usage(pipeline, pixel_usage_mask, vertex_usage_mask))\n"
        "            return false;\n"
        "        for (u32 i = 0; i < XR_VK_PIXEL_TEXTURE_SLOTS; ++i)\n"
        "            if ((pixel_usage_mask & (1u << i)) && !resolved_textures.pixel[i])\n"
        "                return false;\n"
        "        for (u32 i = 0; i < XR_VK_VERTEX_TEXTURE_SLOTS; ++i)\n"
        "            if ((vertex_usage_mask & (1u << i)) && !resolved_textures.vertex[i])\n"
        "                return false;\n"
    )
    if usage_guard not in final:
        if full_sparse_guard in final:
            final = final.replace(full_sparse_guard, usage_guard, 1)
        else:
            resolve_marker = (
                "        if (!xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,\n"
                "                vertex_textures, vertex_texture_count, resolved_textures))\n"
                "            return false;\n"
            )
            if resolve_marker not in final:
                raise RuntimeError("Vulkan descriptor materialization bridge: texture resolution marker missing")
            final = final.replace(resolve_marker, resolve_marker + usage_guard, 1)

    source.write_text(final, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    if _STATIC_SENTINEL in final:
        raise RuntimeError("Vulkan descriptor materialization bridge: temporary boundary sentinel leaked")
    for token in (
        "xr_vk_backend_draw_resources_ready(VkPipeline pipeline",
        "xr_vk_backend_draw_resources_ready(pipeline, vertex_constants",
        "xr_vk_find_pipeline_texture_usage(pipeline, pixel_usage_mask, vertex_usage_mask)",
        "pixel_usage_mask & (1u << i)",
        "vertex_usage_mask & (1u << i)",
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan descriptor materialization bridge validation failed: missing {token}")
    if full_sparse_guard in final:
        raise RuntimeError("Vulkan descriptor materialization bridge: obsolete all-21-slots sparse guard remains")

    print("[vulkan-backend-descriptor-bridge] sparse PS/VS slots are accepted only when SPIR-V reflection proves them statically unused; dynamic indexing remains fail-closed")
