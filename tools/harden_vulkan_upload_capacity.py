from __future__ import annotations

import argparse
from pathlib import Path

UPLOAD_CAPACITY = 64 * 1024 * 1024


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan upload capacity hardening requires materialized render core")

    text = source.read_text(encoding="utf-8")
    old = '''        if (!xr_vk_create_buffer(4 * 1024 * 1024,
                VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_upload_buffer, g_upload_memory))
'''
    new = f'''        if (!xr_vk_create_buffer({UPLOAD_CAPACITY}ull,
                VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, g_upload_buffer, g_upload_memory))
'''
    if f"xr_vk_create_buffer({UPLOAD_CAPACITY}ull" not in text:
        if old not in text:
            raise RuntimeError("Vulkan upload capacity: 4 MiB upload-buffer marker not found")
        text = text.replace(old, new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    if f"xr_vk_create_buffer({UPLOAD_CAPACITY}ull" not in final:
        raise RuntimeError("Vulkan upload capacity validation failed")
    if "xr_vk_create_buffer(4 * 1024 * 1024" in final:
        raise RuntimeError("Vulkan upload capacity validation failed: legacy 4 MiB buffer remains")

    print("[vulkan-upload] upload/staging capacity raised from 4 MiB to 64 MiB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Raise RC6 Vulkan host-visible upload capacity for large texture/geometry transfers.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
