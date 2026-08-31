from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    cache_header = root.resolve() / "xr_3da" / "r_constants_cache.h"
    for path in (source, cache_header):
        if not path.is_file():
            raise FileNotFoundError(path)

    cache_text = cache_header.read_text(encoding="utf-8")
    for token in ("ICF const T* access(u32 id) const", "ICF u32 r_hi() const", "const t_f& get_array_f() const"):
        if token not in cache_text:
            raise RuntimeError(f"constant snapshot requires const-safe cache readback: missing {token}")

    text = source.read_text(encoding="utf-8")
    if "xr_vk_upload_uniform_block" not in text:
        raise RuntimeError("constant snapshot requires Vulkan uniform stream")

    marker = "    VkDeviceSize xr_vk_align_uniform_offset(VkDeviceSize value, VkDeviceSize alignment)\n"
    helper = r'''    struct xr_vk_constant_snapshot
    {
        Fvector4 vertex[256];
        Fvector4 pixel[256];
    };

    bool xr_vk_build_constant_snapshot(const R_constant_array* vertex_constants,
        const R_constant_array* pixel_constants, xr_vk_constant_snapshot& snapshot)
    {
        if (!vertex_constants || !pixel_constants)
            return false;
        memset(&snapshot, 0, sizeof(snapshot));

        const R_constant_array::t_f& vertex = vertex_constants->get_array_f();
        const R_constant_array::t_f& pixel = pixel_constants->get_array_f();
        const u32 vertex_hi = vertex.r_hi();
        const u32 pixel_hi = pixel.r_hi();
        if (vertex_hi > 256 || pixel_hi > 256)
            return false;

        if (vertex_hi)
            memcpy(snapshot.vertex, vertex.access(0), sizeof(Fvector4) * vertex_hi);
        if (pixel_hi)
            memcpy(snapshot.pixel, pixel.access(0), sizeof(Fvector4) * pixel_hi);
        return true;
    }

    bool xr_vk_upload_constant_snapshot(const R_constant_array* vertex_constants,
        const R_constant_array* pixel_constants, VkDeviceSize& uniform_offset, VkDeviceSize& uniform_range)
    {
        uniform_offset = 0;
        uniform_range = 0;
        xr_vk_constant_snapshot snapshot;
        if (!xr_vk_build_constant_snapshot(vertex_constants, pixel_constants, snapshot))
            return false;
        if (!xr_vk_upload_uniform_block(&snapshot, sizeof(snapshot), uniform_offset))
            return false;
        uniform_range = sizeof(snapshot);
        return true;
    }

'''
    if "struct xr_vk_constant_snapshot" not in text:
        if marker not in text:
            raise RuntimeError("constant snapshot insertion marker missing")
        text = text.replace(marker, helper + marker, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_constant_snapshot",
        "Fvector4 vertex[256];",
        "Fvector4 pixel[256];",
        "vertex_constants->get_array_f()",
        "pixel_constants->get_array_f()",
        "vertex.r_hi()",
        "pixel.r_hi()",
        "memset(&snapshot, 0, sizeof(snapshot))",
        "memcpy(snapshot.vertex, vertex.access(0), sizeof(Fvector4) * vertex_hi)",
        "memcpy(snapshot.pixel, pixel.access(0), sizeof(Fvector4) * pixel_hi)",
        "xr_vk_upload_uniform_block(&snapshot, sizeof(snapshot), uniform_offset)",
        "uniform_range = sizeof(snapshot);",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"constant snapshot validation failed: missing {token}")

    print("[vulkan-constant-snapshot] fixed 8192-byte VS[256]+PS[256] float-register UBO snapshot installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serialize SHOC VS/PS float constant caches into a stable Vulkan UBO snapshot.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
