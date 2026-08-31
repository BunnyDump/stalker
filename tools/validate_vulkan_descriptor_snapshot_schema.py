from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    cache_header = root / "xr_3da" / "r_constants_cache.h"
    for path in (source, cache_header):
        if not path.is_file():
            raise FileNotFoundError(path)

    vk = source.read_text(encoding="utf-8")
    cache = cache_header.read_text(encoding="utf-8")

    cache_tokens = (
        "ICF const T* access(u32 id) const",
        "ICF u32 r_lo() const",
        "ICF u32 r_hi() const",
        "const t_f& get_array_f() const",
    )
    for token in cache_tokens:
        if token not in cache:
            raise RuntimeError(f"const-safe constant cache ABI missing {token}")

    descriptor_tokens = (
        "VkDescriptorSetLayoutBinding bindings[3]",
        "bindings[1].descriptorCount = 16;",
        "bindings[1].stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT;",
        "bindings[2].descriptorCount = 5;",
        "bindings[2].stageFlags = VK_SHADER_STAGE_VERTEX_BIT;",
        "descriptor_layout.bindingCount = 3;",
        "pool_sizes[1].descriptorCount = 172032;",
        "XR_VK_PS_TEXTURE_SLOTS = 16",
        "XR_VK_VS_TEXTURE_SLOTS = 5",
        "xr_vk_allocate_snapshot_descriptor",
        "write.dstBinding = 1;",
        "write.dstBinding = 2;",
        "write.dstArrayElement = i;",
    )
    for token in descriptor_tokens:
        if token not in vk:
            raise RuntimeError(f"21-slot descriptor ABI missing {token}")

    constant_tokens = (
        "struct xr_vk_constant_snapshot",
        "Fvector4 vertex[256];",
        "Fvector4 pixel[256];",
        "memset(&snapshot, 0, sizeof(snapshot))",
        "vertex.r_hi()",
        "pixel.r_hi()",
        "xr_vk_upload_uniform_block(&snapshot, sizeof(snapshot), uniform_offset)",
        "uniform_range = sizeof(snapshot);",
    )
    for token in constant_tokens:
        if token not in vk:
            raise RuntimeError(f"constant snapshot ABI missing {token}")

    # 256 float4 registers per stage, two stages, 16 bytes per register.
    if "Fvector4 vertex[256];" not in vk or "Fvector4 pixel[256];" not in vk:
        raise RuntimeError("constant snapshot is not the expected fixed 8192-byte VS+PS register image")

    # Safety boundary: sparse descriptor slots are deliberately not populated with null descriptors.
    # Production draw remains closed until shader-side binding usage is validated against the snapshot.
    if "if (!resource)\n                continue;" not in vk:
        raise RuntimeError("descriptor snapshot no longer preserves sparse legacy texture slots safely")
    if "return false;" not in vk[vk.index("xr_vk_backend_draw_resources_ready"):vk.index("bool xr_vk_record_dynamic_indexed_backend_draw")]:
        raise RuntimeError("production resource gate opened before descriptor/shader contract validation")

    print("[validate-vulkan-descriptor-snapshot] UBO + PS[16] + VS[5] ABI and fixed VS/PS constant snapshot are structurally safe; production gate remains fail-closed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vulkan SHOC descriptor schema and constant snapshot ABI.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
