from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8", errors="strict")

    state_marker = "static unsigned g_vk_material_lut = 0;\n"
    state = state_marker + "static unsigned g_vk_jitter[TEX_jitter_count] = {0};\n"
    if "g_vk_jitter[TEX_jitter_count]" not in text:
        if state_marker not in text:
            raise RuntimeError("jitter state marker not found")
        text = text.replace(state_marker, state, 1)

    lock_block = (
        "\t\t\tD3DLOCKED_RECT R[TEX_jitter_count];\n"
        "\t\t\tfor (int it = 0; it < TEX_jitter_count; it++)\n"
    )
    cpu_block = (
        "\t\t\txr_vector<u32> vk_jitter[TEX_jitter_count];\n"
        "\t\t\tfor (int it = 0; it < TEX_jitter_count; ++it)\n"
        "\t\t\t\tvk_jitter[it].resize(TEX_jitter * TEX_jitter);\n"
    )
    if "vk_jitter[it].resize" not in text:
        if lock_block not in text:
            raise RuntimeError("jitter lock block marker not found")
        text = text.replace(lock_block, "\t\t\tD3DLOCKED_RECT R[TEX_jitter_count];\n" + cpu_block + "\t\t\tfor (int it = 0; it < TEX_jitter_count; it++)\n", 1)

    store_marker = "\t\t\t\t\t\t*p = data[it];\n"
    store = store_marker + "\t\t\t\t\t\tvk_jitter[it][y * TEX_jitter + x] = data[it];\n"
    if "vk_jitter[it][y * TEX_jitter + x]" not in text:
        if store_marker not in text:
            raise RuntimeError("jitter store marker not found")
        text = text.replace(store_marker, store, 1)

    unlock_block = (
        "\t\t\tfor (int it = 0; it < TEX_jitter_count; it++)\n"
        "\t\t\t{\n"
        "\t\t\t\tR_CHK(t_noise_surf[it]->UnlockRect(0));\n"
        "\t\t\t}\n"
    )
    upload = unlock_block + (
        "\t\t\tif (xr_vk_bootstrap_runtime_ready())\n"
        "\t\t\t{\n"
        "\t\t\t\tfor (u32 it = 0; it < TEX_jitter_count; ++it)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tif (!g_vk_jitter[it])\n"
        "\t\t\t\t\t\tg_vk_jitter[it] = xr_vk_texture_create(&vk_jitter[it][0], TEX_jitter, TEX_jitter, 1, XR_VK_TEXTURE_RGBA8_SNORM);\n"
        "\t\t\t\t\tif (!g_vk_jitter[it])\n"
        "\t\t\t\t\t\tMsg(\"! [X-Ray Vulkan] Failed to upload jitter texture %u; legacy texture remains active.\", it);\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
    )
    if "Failed to upload jitter texture" not in text:
        if unlock_block not in text:
            raise RuntimeError("jitter unlock block marker not found")
        text = text.replace(unlock_block, upload, 1)

    cleanup_marker = (
        "\tfor (int it = 0; it < TEX_jitter_count; it++)\n"
        "\t{\n"
        "\t\tt_noise[it]->surface_set(NULL);\n"
    )
    cleanup = cleanup_marker + (
        "\t\tif (g_vk_jitter[it])\n"
        "\t\t{\n"
        "\t\t\txr_vk_texture_destroy(g_vk_jitter[it]);\n"
        "\t\t\tg_vk_jitter[it] = 0;\n"
        "\t\t}\n"
    )
    if "xr_vk_texture_destroy(g_vk_jitter[it])" not in text:
        if cleanup_marker not in text:
            raise RuntimeError("jitter cleanup marker not found")
        text = text.replace(cleanup_marker, cleanup, 1)

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in (
        "g_vk_jitter[TEX_jitter_count]",
        "vk_jitter[it].resize",
        "XR_VK_TEXTURE_RGBA8_SNORM",
        "xr_vk_texture_create(&vk_jitter[it][0]",
        "xr_vk_texture_destroy(g_vk_jitter[it])",
    ):
        if token not in final:
            raise RuntimeError(f"jitter Vulkan validation missing {token}")
    print("[vulkan-jitter] R2 procedural jitter textures mirrored to native Vulkan RGBA8_SNORM images")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror procedural R2 jitter textures into native Vulkan sampled images.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
