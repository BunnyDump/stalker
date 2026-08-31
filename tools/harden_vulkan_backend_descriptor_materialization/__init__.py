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

    # The static-geometry installer places the registration exports before both static
    # draw recorders. The canonical materializer historically used the registration
    # export as the right-hand boundary of xr_vk_record_static_backend_draw(), which
    # therefore resolves to -1. Add a temporary textual sentinel immediately before the
    # backend draw export so its existing range logic selects exactly the static recorder.
    # The sentinel is removed again after materialization and never reaches C++ compilation.
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

    # The descriptor schema deliberately leaves null legacy texture slots unwritten.
    # Without descriptor indexing / partially-bound support, submitting such a set is not
    # a safe production path. Until shader reflection or a dedicated null texture fills
    # those slots, accept Vulkan only when the complete PS[16]+VS[5] snapshot is backed by
    # shader-readable resources. All sparse draws retain the existing D3D9 fallback.
    final = source.read_text(encoding="utf-8")
    resolve_marker = (
        "        if (!xr_vk_resolve_texture_snapshot(pixel_textures, pixel_texture_count,\n"
        "                vertex_textures, vertex_texture_count, resolved_textures))\n"
        "            return false;\n"
    )
    sparse_guard = resolve_marker + (
        "        for (u32 i = 0; i < XR_VK_PIXEL_TEXTURE_SLOTS; ++i)\n"
        "            if (!resolved_textures.pixel[i])\n"
        "                return false;\n"
        "        for (u32 i = 0; i < XR_VK_VERTEX_TEXTURE_SLOTS; ++i)\n"
        "            if (!resolved_textures.vertex[i])\n"
        "                return false;\n"
    )
    if "if (!resolved_textures.pixel[i])" not in final:
        if resolve_marker not in final:
            raise RuntimeError("Vulkan descriptor materialization bridge: resolved texture gate marker missing")
        final = final.replace(resolve_marker, sparse_guard, 1)
        source.write_text(final, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    if _STATIC_SENTINEL in final:
        raise RuntimeError("Vulkan descriptor materialization bridge: temporary boundary sentinel leaked")
    for token in (
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, descriptor_set, primitive",
        "xr_vk_bind_material_descriptor(command_buffer, descriptor_set)",
        "if (!resolved_textures.pixel[i])",
        "if (!resolved_textures.vertex[i])",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan descriptor materialization bridge validation failed: missing {token}")

    print("[vulkan-backend-descriptor-bridge] static boundary repaired; sparse descriptor sets fail closed to D3D9 fallback")
