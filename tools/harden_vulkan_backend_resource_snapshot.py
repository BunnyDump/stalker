from __future__ import annotations

import argparse
from pathlib import Path


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
    if "const R_constant_array* vertex_constants" not in h:
        h = replace_once(
            h,
            "    IDirect3DPixelShader9* pixel_shader, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n"
            "    u32 start_index, u32 primitive_count);",
            "    IDirect3DPixelShader9* pixel_shader, const R_constant_array* vertex_constants,\n"
            "    const R_constant_array* pixel_constants, CTexture* const* pixel_textures, u32 pixel_texture_count,\n"
            "    CTexture* const* vertex_textures, u32 vertex_texture_count, u32 base_vertex, u32 start_vertex,\n"
            "    u32 vertex_count, u32 start_index, u32 primitive_count);",
            "indexed resource-snapshot ABI",
        )
        h = replace_once(
            h,
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    u32 start_vertex, u32 primitive_count);",
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    const R_constant_array* vertex_constants, const R_constant_array* pixel_constants,\n"
            "    CTexture* const* pixel_textures, u32 pixel_texture_count, CTexture* const* vertex_textures,\n"
            "    u32 vertex_texture_count, u32 start_vertex, u32 primitive_count);",
            "non-indexed resource-snapshot ABI",
        )
        backend_h.write_text(h, encoding="utf-8")

    rt = backend_runtime.read_text(encoding="utf-8")
    indexed_old = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV, startV, countV, startI, PC)"
    indexed_new = (
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, &constants.a_vertex, "
        "&constants.a_pixel, textures_ps, 16, textures_vs, 5, baseV, startV, countV, startI, PC)"
    )
    if indexed_new not in rt:
        rt = replace_once(rt, indexed_old, indexed_new, "indexed resource-snapshot call")

    plain_old = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV, PC)"
    plain_new = (
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, &constants.a_vertex, &constants.a_pixel, "
        "textures_ps, 16, textures_vs, 5, startV, PC)"
    )
    if plain_new not in rt:
        rt = replace_once(rt, plain_old, plain_new, "non-indexed resource-snapshot call")
    backend_runtime.write_text(rt, encoding="utf-8")

    vk = vk_source.read_text(encoding="utf-8")
    if "CTexture* const* pixel_textures" not in vk[vk.find('xrRender_vk_backend_draw_indexed'):]:
        vk = replace_once(
            vk,
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    u32 base_vertex, u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)",
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    const R_constant_array* vertex_constants, const R_constant_array* pixel_constants,\n"
            "    CTexture* const* pixel_textures, u32 pixel_texture_count, CTexture* const* vertex_textures,\n"
            "    u32 vertex_texture_count, u32 base_vertex, u32 start_vertex, u32 vertex_count,\n"
            "    u32 start_index, u32 primitive_count)",
            "indexed Vulkan export resource snapshot",
        )
        vk = replace_once(
            vk,
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    u32 start_vertex, u32 primitive_count)",
            "    IDirect3DVertexShader9* vertex_shader, IDirect3DPixelShader9* pixel_shader,\n"
            "    const R_constant_array* vertex_constants, const R_constant_array* pixel_constants,\n"
            "    CTexture* const* pixel_textures, u32 pixel_texture_count, CTexture* const* vertex_textures,\n"
            "    u32 vertex_texture_count, u32 start_vertex, u32 primitive_count)",
            "non-indexed Vulkan export resource snapshot",
        )

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

    required = {
        backend_h: (
            "const R_constant_array* vertex_constants",
            "CTexture* const* pixel_textures",
            "u32 pixel_texture_count",
            "u32 vertex_texture_count",
        ),
        backend_runtime: (
            "&constants.a_vertex, &constants.a_pixel, textures_ps, 16, textures_vs, 5",
        ),
        vk_source: (
            "xr_vk_backend_draw_resources_ready(const R_constant_array* vertex_constants",
            "pixel_texture_count != 16 || vertex_texture_count != 5",
            "xr_vk_backend_draw_resources_ready(vertex_constants, pixel_constants, pixel_textures, pixel_texture_count",
        ),
    }
    for path, tokens in required.items():
        final = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in final:
                raise RuntimeError(f"Vulkan backend resource snapshot validation failed in {path.name}: missing {token}")

    print("[vulkan-backend-resources] exact CBackend constant caches + 16 PS/5 VS texture slots now cross the production Vulkan draw ABI; descriptor materialization remains fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carry the exact SHOC CBackend texture/constant snapshot into production Vulkan draw dispatch.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
