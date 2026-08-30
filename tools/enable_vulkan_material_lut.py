from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8", errors="strict")

    include_marker = '#include "blender_luminance.h"\n'
    if '#include "vk_bootstrap.h"' not in text:
        if include_marker not in text:
            raise RuntimeError("material LUT include marker not found")
        text = text.replace(include_marker, include_marker + '#include "vk_bootstrap.h"\n', 1)

    state_marker = '#include "vk_bootstrap.h"\n'
    state = state_marker + '\nstatic unsigned g_vk_material_lut = 0;\n'
    if "g_vk_material_lut" not in text:
        text = text.replace(state_marker, state, 1)

    lock_marker = '\t\t\tD3DLOCKED_BOX R;\n\t\t\tR_CHK(t_material_surf->LockBox(0, &R, 0, 0));\n'
    cpu_buffer = (
        '\t\t\txr_vector<u8> vk_material_lut;\n'
        '\t\t\tvk_material_lut.resize(TEX_material_LdotN * TEX_material_LdotH * 4 * 2);\n'
    )
    if "vk_material_lut.resize" not in text:
        if lock_marker not in text:
            raise RuntimeError("material LUT lock marker not found")
        text = text.replace(lock_marker, cpu_buffer + lock_marker, 1)

    store_marker = '\t\t\t\t\t\t*p = u16(_s * 256 + _d);\n'
    store = store_marker + (
        '\t\t\t\t\t\tconst u32 vk_index = ((slice * TEX_material_LdotH + y) * TEX_material_LdotN + x) * 2;\n'
        '\t\t\t\t\t\tvk_material_lut[vk_index + 0] = u8(_d);\n'
        '\t\t\t\t\t\tvk_material_lut[vk_index + 1] = u8(_s);\n'
    )
    if "const u32 vk_index" not in text:
        if store_marker not in text:
            raise RuntimeError("material LUT store marker not found")
        text = text.replace(store_marker, store, 1)

    unlock_marker = '\t\t\tR_CHK(t_material_surf->UnlockBox(0));\n'
    upload = unlock_marker + (
        '\t\t\tif (xr_vk_bootstrap_runtime_ready() && !g_vk_material_lut)\n'
        '\t\t\t{\n'
        '\t\t\t\tg_vk_material_lut = xr_vk_texture_create(&vk_material_lut[0], TEX_material_LdotN, TEX_material_LdotH, 4, XR_VK_TEXTURE_RG8_UNORM);\n'
        '\t\t\t\tif (!g_vk_material_lut)\n'
        '\t\t\t\t\tMsg("! [X-Ray Vulkan] Failed to upload material LUT; legacy texture remains active.");\n'
        '\t\t\t}\n'
    )
    if "Failed to upload material LUT" not in text:
        if unlock_marker not in text:
            raise RuntimeError("material LUT unlock marker not found")
        text = text.replace(unlock_marker, upload, 1)

    destructor_marker = '\tt_material->surface_set(NULL);\n'
    cleanup = destructor_marker + (
        '\tif (g_vk_material_lut)\n'
        '\t{\n'
        '\t\txr_vk_texture_destroy(g_vk_material_lut);\n'
        '\t\tg_vk_material_lut = 0;\n'
        '\t}\n'
    )
    if "xr_vk_texture_destroy(g_vk_material_lut)" not in text:
        if destructor_marker not in text:
            raise RuntimeError("material LUT destructor marker not found")
        text = text.replace(destructor_marker, cleanup, 1)

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in (
        '#include "vk_bootstrap.h"',
        "g_vk_material_lut",
        "vk_material_lut.resize",
        "XR_VK_TEXTURE_RG8_UNORM",
        "xr_vk_texture_create(&vk_material_lut[0]",
        "xr_vk_texture_destroy(g_vk_material_lut)",
    ):
        if token not in final:
            raise RuntimeError(f"material LUT validation missing {token}")
    print("[vulkan-material-lut] R2 material LUT mirrored to native Vulkan 3D RG8 texture")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror the procedural R2 material LUT into a native Vulkan 3D texture.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
