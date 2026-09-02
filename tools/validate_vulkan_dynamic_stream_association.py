from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    h_path = root / "xr_3da" / "R_DStreams.h"
    cpp_path = root / "xr_3da" / "R_DStreams.cpp"
    api_path = root / "xr_3da" / "EngineAPI.cpp"
    vk_path = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (h_path, cpp_path, api_path, vk_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = h_path.read_text(encoding="utf-8")
    cpp = cpp_path.read_text(encoding="utf-8")
    api = api_path.read_text(encoding="utf-8")
    vk = vk_path.read_text(encoding="utf-8")

    for token in (
        "xr_vk_vertex_stream_upload_fn", "xr_vk_index_stream_upload_fn",
        "IDirect3DVertexBuffer9* source", "IDirect3DIndexBuffer9* source",
        "void* vkLockData;", "u32 vkLockOffset;",
    ):
        if token not in h:
            raise RuntimeError(f"dynamic stream association header validation failed: missing {token}")

    if h.count("void* vkLockData;") != 2 or h.count("u32 vkLockOffset;") != 2:
        raise RuntimeError("dynamic stream association header validation failed: lock metadata must exist once per stream")

    vertex_lock_start = cpp.find("void* _VertexStream::Lock")
    vertex_unlock_start = cpp.find("void _VertexStream::Unlock", vertex_lock_start)
    index_lock_start = cpp.find("u16* _IndexStream::Lock", vertex_unlock_start)
    index_unlock_start = cpp.find("void _IndexStream::Unlock", index_lock_start)
    if min(vertex_lock_start, vertex_unlock_start, index_lock_start, index_unlock_start) < 0:
        raise RuntimeError("dynamic stream association validation failed: stream method boundaries missing")

    vertex_lock = cpp[vertex_lock_start:vertex_unlock_start]
    vertex_unlock = cpp[vertex_unlock_start:index_lock_start]
    index_lock = cpp[index_lock_start:index_unlock_start]
    index_unlock = cpp[index_unlock_start:]

    for label, block, tokens in (
        ("vertex lock", vertex_lock, ("vkLockData = pData;", "vkLockOffset = mPosition;")),
        ("vertex unlock", vertex_unlock, ("g_xr_vk_vertex_stream_upload(pVB, vkLockData", "vkLockData = NULL;", "pVB->Unlock();")),
        ("index lock", index_lock, ("vkLockData = pLockedData;", "vkLockOffset = mPosition * 2;")),
        ("index unlock", index_unlock, ("g_xr_vk_index_stream_upload(pIB, vkLockData", "vkLockData = NULL;", "pIB->Unlock();")),
    ):
        for token in tokens:
            if token not in block:
                raise RuntimeError(f"dynamic stream association validation failed in {label}: missing {token}")

    if vertex_unlock.find("g_xr_vk_vertex_stream_upload(pVB") > vertex_unlock.find("pVB->Unlock();"):
        raise RuntimeError("dynamic stream association validation failed: vertex upload occurs after WRITEONLY D3D unlock")
    if index_unlock.find("g_xr_vk_index_stream_upload(pIB") > index_unlock.find("pIB->Unlock();"):
        raise RuntimeError("dynamic stream association validation failed: index upload occurs after WRITEONLY D3D unlock")

    for token in (
        'GetProcAddress(hRender, "xrRender_vk_vertex_stream_upload")',
        'GetProcAddress(hRender, "xrRender_vk_index_stream_upload")',
        "g_xr_vk_vertex_stream_upload = NULL;", "g_xr_vk_index_stream_upload = NULL;",
    ):
        if token not in api:
            raise RuntimeError(f"dynamic stream association EngineAPI validation failed: missing {token}")

    for token in (
        "IDirect3DVertexBuffer9* g_stream_vertex_source", "IDirect3DIndexBuffer9* g_stream_index_source",
        "g_stream_vertex_discard_id", "g_stream_index_discard_id",
        "g_stream_vertex_valid_begin", "g_stream_vertex_valid_end",
        "g_stream_index_valid_begin", "g_stream_index_valid_end",
        "xrRender_vk_vertex_stream_upload", "xrRender_vk_index_stream_upload",
        "xr_vk_dynamic_vertex_range_ready", "xr_vk_dynamic_index_range_ready",
        "source != g_stream_vertex_source", "source != g_stream_index_source",
        "begin < g_stream_vertex_valid_begin || end > g_stream_vertex_valid_end",
        "begin < g_stream_index_valid_begin || end > g_stream_index_valid_end",
        "begin > g_stream_vertex_valid_end || end < g_stream_vertex_valid_begin",
        "begin > g_stream_index_valid_end || end < g_stream_index_valid_begin",
    ):
        if token not in vk:
            raise RuntimeError(f"dynamic stream association Vulkan validation failed: missing {token}")

    vertex_upload_start = vk.find('xrRender_vk_vertex_stream_upload')
    index_upload_start = vk.find('xrRender_vk_index_stream_upload', vertex_upload_start)
    vertex_range_start = vk.find('xr_vk_dynamic_vertex_range_ready', index_upload_start)
    index_range_start = vk.find('xr_vk_dynamic_index_range_ready', vertex_range_start)
    backend_start = vk.find('xrRender_vk_backend_draw_indexed', index_range_start)
    if min(vertex_upload_start, index_upload_start, vertex_range_start, index_range_start, backend_start) < 0:
        raise RuntimeError("dynamic stream association Vulkan validation failed: helper/export ordering missing")

    # Disjoint NOOVERWRITE writes must restart the exact valid interval. Otherwise bytes
    # that were never mirrored could be accepted by a later draw range check.
    for prefix in ("vertex", "index"):
        condition = f"begin > g_stream_{prefix}_valid_end || end < g_stream_{prefix}_valid_begin"
        pos = vk.find(condition)
        if pos < 0:
            raise RuntimeError(f"dynamic stream association validation failed: {prefix} gap condition missing")
        block = vk[pos:pos + 700]
        for assignment in (
            f"g_stream_{prefix}_valid_begin = begin;",
            f"g_stream_{prefix}_valid_end = end;",
        ):
            if assignment not in block:
                raise RuntimeError(f"dynamic stream association validation failed: {prefix} gap does not reset exact interval")

    destroy_start = vk.find("void xr_vk_destroy_frame_resources()")
    destroy_end = vk.find("void xr_vk_destroy_window_runtime()", destroy_start)
    if destroy_start < 0 or destroy_end < 0:
        raise RuntimeError("dynamic stream association validation failed: shutdown boundaries missing")
    destroy = vk[destroy_start:destroy_end]
    for token in (
        "g_stream_vertex_source = NULL;", "g_stream_index_source = NULL;",
        "g_stream_vertex_valid_begin = g_stream_vertex_valid_end = 0;",
        "g_stream_index_valid_begin = g_stream_index_valid_end = 0;",
    ):
        if token not in destroy:
            raise RuntimeError(f"dynamic stream association shutdown validation failed: missing {token}")

    # The dynamic index stream in SHOC is explicitly D3DFMT_INDEX16. Static or 32-bit
    # index buffers must not be silently treated as the dynamic mirror.
    if "static_cast<VkDeviceSize>(first_index) * sizeof(u16)" not in vk:
        raise RuntimeError("dynamic stream association validation failed: SHOC dynamic index stride is not explicit")

    print("[vulkan-dynamic-stream-association] WRITEONLY Lock/Unlock upload order + gap-safe source/discard/range identity + shutdown reset verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate safe SHOC D3D9 dynamic-stream association with Vulkan mirrors.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
