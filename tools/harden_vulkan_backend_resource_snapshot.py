from __future__ import annotations

import argparse
from pathlib import Path

from harden_vulkan_backend_static_resource_snapshot import harden as harden_vulkan_backend_static_resource_snapshot
from validate_vulkan_backend_static_draw import validate as validate_vulkan_backend_static_draw


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old, new, 1)


def harden(root: Path) -> None:
    root = root.resolve()
    backend_h = root / "xr_3da" / "R_Backend.h"
    backend_runtime = root / "xr_3da" / "R_Backend_Runtime.h"
    vk_source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (backend_h, backend_runtime, vk_source):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = backend_h.read_text(encoding="utf-8")
    if h.count("const R_constant_array* vertex_constants") < 2:
        h = replace_once(
            h,
            "    IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n"
            "    IDirect3DStateBlock9* state_block, const xr_vk_render_state_snapshot* render_state, u32 base_vertex, "
            "u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count);",
            "    IDirect3DPixelShader9* pixel_shader, LPCSTR vertex_shader_name, LPCSTR pixel_shader_name,\n"
            "    IDirect3DStateBlock9* state_block, const xr_vk_render_state_snapshot* render_state,\n"
            "    const R_constant_array* vertex_constants, const R_constant_array* pixel_constants,\n"
            "    CTexture* const* pixel_textures, u32 pixel_texture_count, CTexture* const* vertex_textures,\n"
            "    u32 vertex_texture_count, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n"
            "    u32 start_index, u32 primitive_count);",
            "indexed state-aware resource-snapshot ABI",
        )
        h = replace_once(
            h,
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, u32 start_vertex, u32 primitive_count);",
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, const R_constant_array* vertex_constants,\n"
            "    const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
            "    CTexture* const* vertex_textures, u32 vertex_texture_count, u32 start_vertex, u32 primitive_count);",
            "non-indexed state-aware resource-snapshot ABI",
        )
        backend_h.write_text(h, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")
    indexed_old = (
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, state, "
        "vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, baseV, startV, countV, startI, PC)"
    )
    indexed_new = (
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, state, "
        "vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, &constants.a_vertex, &constants.a_pixel, "
        "textures_ps, 16, textures_vs, 5, baseV, startV, countV, startI, PC)"
    )
    if indexed_new not in rt:
        rt = replace_once(rt, indexed_old, indexed_new, "indexed state-aware resource-snapshot call")

    plain_old = (
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, state, "
        "vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, startV, PC)"
    )
    plain_new = (
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, state, "
        "vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, &constants.a_vertex, &constants.a_pixel, "
        "textures_ps, 16, textures_vs, 5, startV, PC)"
    )
    if plain_new not in rt:
        rt = replace_once(rt, plain_old, plain_new, "non-indexed state-aware resource-snapshot call")
    backend_runtime.write_text(rt, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    indexed_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan backend resource snapshot: renderer exports missing")

    indexed_block = vk[indexed_start:plain_start]
    if "const R_constant_array* vertex_constants" not in indexed_block:
        old = (
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, u32 base_vertex, u32 start_vertex, "
            "u32 vertex_count, u32 start_index, u32 primitive_count)"
        )
        new = (
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, const R_constant_array* vertex_constants,\n"
            "    const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
            "    CTexture* const* vertex_textures, u32 vertex_texture_count, u32 base_vertex, u32 start_vertex,\n"
            "    u32 vertex_count, u32 start_index, u32 primitive_count)"
        )
        indexed_block = replace_once(indexed_block, old, new, "indexed Vulkan export resource snapshot")
        vk = vk[:indexed_start] + indexed_block + vk[plain_start:]

    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain_block = vk[plain_start:]
    if "const R_constant_array* vertex_constants" not in plain_block:
        old = (
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, u32 start_vertex, u32 primitive_count)"
        )
        new = (
            "    LPCSTR vertex_shader_name, LPCSTR pixel_shader_name, IDirect3DStateBlock9* state_block,\n"
            "    const xr_vk_render_state_snapshot* render_state, const R_constant_array* vertex_constants,\n"
            "    const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
            "    CTexture* const* vertex_textures, u32 vertex_texture_count, u32 start_vertex, u32 primitive_count)"
        )
        plain_block = replace_once(plain_block, old, new, "non-indexed Vulkan export resource snapshot")
        vk = vk[:plain_start] + plain_block

    gate_old = "    bool xr_vk_backend_draw_resources_ready()\n    {\n"
    gate_new = (
        "    bool xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants,\n"
        "        const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
        "        CTexture* const* vertex_textures, u32 vertex_texture_count)\n"
        "    {\n"
        "        if (!vertex_constants || !pixel_constants || !pixel_textures || !vertex_textures ||\n"
        "            pixel_texture_count != 16 || vertex_texture_count != 5)\n"
        "            return false;\n"
    )
    if "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants" not in vk:
        vk = replace_once(vk, gate_old, gate_new, "resource gate snapshot signature")

    gate_call_old = "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_indexed_backend_draw"
    gate_call_new = (
        "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_indexed_backend_draw"
    )
    if gate_call_new not in vk:
        vk = replace_once(vk, gate_call_old, gate_call_new, "indexed resource gate call")

    gate_plain_old = "xr_vk_backend_draw_resources_ready() &&\n        xr_vk_record_dynamic_backend_draw"
    gate_plain_new = (
        "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count,\n"
        "            vertex_textures, vertex_texture_count) &&\n"
        "        xr_vk_record_dynamic_backend_draw"
    )
    if gate_plain_new not in vk:
        vk = replace_once(vk, gate_plain_old, gate_plain_new, "non-indexed resource gate call")

    vk_source.write_text(vk, encoding="utf-8")

    # Static level/model Vulkan calls share the exact same state-aware resource snapshot.
    # Adapt them only after the common gate signature has changed.
    harden_vulkan_backend_static_resource_snapshot(root)
    validate_vulkan_backend_static_draw(root)

    required = {
        backend_h: (
            "const R_constant_array* vertex_constants",
            "CTexture* const* pixel_textures",
            "u32 pixel_texture_count",
            "u32 vertex_texture_count",
        ),
        backend_runtime: (
            "vk_render_state_snapshot_valid ? &vk_render_state_snapshot : NULL, &constants.a_vertex, &constants.a_pixel, textures_ps, 16, textures_vs, 5",
        ),
        vk_source: (
            "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants",
            "pixel_texture_count != 16 || vertex_texture_count != 5",
            "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count",
            "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive",
            "xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive",
        ),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"Vulkan backend resource snapshot validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-resources] state-aware production ABI now carries exact CBackend constant caches + 16 PS/5 VS texture slots across dynamic + static draws; descriptor materialization remains fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry the exact SHOC CBackend texture/constant snapshot into production Vulkan draw dispatch.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
