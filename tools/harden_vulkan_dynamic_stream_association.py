from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    root = root.resolve()
    ds_h = root / "xr_3da" / "R_DStreams.h"
    ds_cpp = root / "xr_3da" / "R_DStreams.cpp"
    api_path = root / "xr_3da" / "EngineAPI.cpp"
    vk_path = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    for path in (ds_h, ds_cpp, api_path, vk_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    h = ds_h.read_text(encoding="utf-8")
    pragma = "#pragma once\n"
    abi = r'''

// Dynamic-stream upload bridge.  Upload happens while the D3D9 WRITEONLY buffer is
// still mapped, so Vulkan never attempts to read a write-only D3D resource later.
typedef BOOL(__cdecl* xr_vk_vertex_stream_upload_fn)(IDirect3DVertexBuffer9* source,
    const void* data, u32 byte_count, u32 byte_offset, u32 discard_id);
typedef BOOL(__cdecl* xr_vk_index_stream_upload_fn)(IDirect3DIndexBuffer9* source,
    const void* data, u32 byte_count, u32 byte_offset, u32 discard_id);
extern ENGINE_API xr_vk_vertex_stream_upload_fn g_xr_vk_vertex_stream_upload;
extern ENGINE_API xr_vk_index_stream_upload_fn g_xr_vk_index_stream_upload;
'''
    if "g_xr_vk_vertex_stream_upload" not in h:
        if pragma not in h:
            raise RuntimeError("dynamic stream association: pragma marker missing")
        h = h.replace(pragma, pragma + abi, 1)

    vertex_fields = "\tu32 mDiscardID; // ID of discard - usually for caching\n"
    vertex_new = vertex_fields + "\tvoid* vkLockData;\n\tu32 vkLockOffset;\n"
    if "void* vkLockData;" not in h:
        if vertex_fields not in h:
            raise RuntimeError("dynamic stream association: vertex field marker missing")
        h = h.replace(vertex_fields, vertex_new, 1)

    index_fields = "\tu32 mDiscardID;\n\n  public:\n\tIDirect3DIndexBuffer9* old_pIB;"
    index_new = "\tu32 mDiscardID;\n\tvoid* vkLockData;\n\tu32 vkLockOffset;\n\n  public:\n\tIDirect3DIndexBuffer9* old_pIB;"
    if h.count("void* vkLockData;") < 2:
        if index_fields not in h:
            raise RuntimeError("dynamic stream association: index field marker missing")
        h = h.replace(index_fields, index_new, 1)

    # Both _clear() methods must clear the transient mapped pointer metadata.
    clear_marker = "\t\tmDiscardID = 0;\n"
    clear_new = clear_marker + "\t\tvkLockData = NULL;\n\t\tvkLockOffset = 0;\n"
    if h.count("vkLockData = NULL;") < 2:
        if h.count(clear_marker) < 2:
            raise RuntimeError("dynamic stream association: clear markers missing")
        h = h.replace(clear_marker, clear_new)
    ds_h.write_text(h, encoding="utf-8")

    cpp = ds_cpp.read_text(encoding="utf-8")
    include_marker = '#include "R_DStreams.h"\n'
    globals_block = include_marker + "\nENGINE_API xr_vk_vertex_stream_upload_fn g_xr_vk_vertex_stream_upload = NULL;\nENGINE_API xr_vk_index_stream_upload_fn g_xr_vk_index_stream_upload = NULL;\n"
    if "g_xr_vk_vertex_stream_upload = NULL" not in cpp:
        if include_marker not in cpp:
            raise RuntimeError("dynamic stream association: R_DStreams include marker missing")
        cpp = cpp.replace(include_marker, globals_block, 1)

    vertex_return = "\tVERIFY(pData);\n\n\treturn LPVOID(pData);\n"
    vertex_return_new = "\tVERIFY(pData);\n\tvkLockData = pData;\n\tvkLockOffset = mPosition;\n\n\treturn LPVOID(pData);\n"
    if "vkLockOffset = mPosition;" not in cpp:
        if vertex_return not in cpp:
            raise RuntimeError("dynamic stream association: vertex lock return marker missing")
        cpp = cpp.replace(vertex_return, vertex_return_new, 1)

    vertex_unlock = "\tmPosition += Count * Stride;\n\n\tVERIFY(pVB);\n\tpVB->Unlock();\n"
    vertex_unlock_new = r'''	const u32 uploaded_bytes = Count * Stride;
	if (g_xr_vk_vertex_stream_upload && vkLockData && uploaded_bytes)
		g_xr_vk_vertex_stream_upload(pVB, vkLockData, uploaded_bytes, vkLockOffset, mDiscardID);
	vkLockData = NULL;
	vkLockOffset = 0;
	mPosition += uploaded_bytes;

	VERIFY(pVB);
	pVB->Unlock();
'''
    if "g_xr_vk_vertex_stream_upload(pVB" not in cpp:
        if vertex_unlock not in cpp:
            raise RuntimeError("dynamic stream association: vertex unlock marker missing")
        cpp = cpp.replace(vertex_unlock, vertex_unlock_new, 1)

    index_return = "\tvOffset = mPosition;\n\n\treturn LPWORD(pLockedData);\n"
    index_return_new = "\tvOffset = mPosition;\n\tvkLockData = pLockedData;\n\tvkLockOffset = mPosition * 2;\n\n\treturn LPWORD(pLockedData);\n"
    if "vkLockOffset = mPosition * 2;" not in cpp:
        if index_return not in cpp:
            raise RuntimeError("dynamic stream association: index lock return marker missing")
        cpp = cpp.replace(index_return, index_return_new, 1)

    index_unlock = "\tmPosition += RealCount;\n\tVERIFY(pIB);\n\tpIB->Unlock();\n"
    index_unlock_new = r'''	const u32 uploaded_bytes = RealCount * 2;
	if (g_xr_vk_index_stream_upload && vkLockData && uploaded_bytes)
		g_xr_vk_index_stream_upload(pIB, vkLockData, uploaded_bytes, vkLockOffset, mDiscardID);
	vkLockData = NULL;
	vkLockOffset = 0;
	mPosition += RealCount;
	VERIFY(pIB);
	pIB->Unlock();
'''
    if "g_xr_vk_index_stream_upload(pIB" not in cpp:
        if index_unlock not in cpp:
            raise RuntimeError("dynamic stream association: index unlock marker missing")
        cpp = cpp.replace(index_unlock, index_unlock_new, 1)
    ds_cpp.write_text(cpp, encoding="utf-8")

    api = api_path.read_text(encoding="utf-8")
    resolve_marker = '''\t\tg_xr_vk_backend_draw = reinterpret_cast<xr_vk_backend_draw_fn>(
\t\t\tGetProcAddress(hRender, "xrRender_vk_backend_draw"));
'''
    resolve_new = resolve_marker + '''\t\tg_xr_vk_vertex_stream_upload = reinterpret_cast<xr_vk_vertex_stream_upload_fn>(
\t\t\tGetProcAddress(hRender, "xrRender_vk_vertex_stream_upload"));
\t\tg_xr_vk_index_stream_upload = reinterpret_cast<xr_vk_index_stream_upload_fn>(
\t\t\tGetProcAddress(hRender, "xrRender_vk_index_stream_upload"));
'''
    if "xrRender_vk_vertex_stream_upload" not in api:
        if resolve_marker not in api:
            raise RuntimeError("dynamic stream association: EngineAPI resolve marker missing")
        api = api.replace(resolve_marker, resolve_new, 1)

    free_marker = "\t\tg_xr_vk_backend_draw = NULL;\n\t\tFreeLibrary(hRender);\n"
    free_new = "\t\tg_xr_vk_backend_draw = NULL;\n\t\tg_xr_vk_vertex_stream_upload = NULL;\n\t\tg_xr_vk_index_stream_upload = NULL;\n\t\tFreeLibrary(hRender);\n"
    if "g_xr_vk_vertex_stream_upload = NULL;\n\t\tg_xr_vk_index_stream_upload = NULL;" not in api:
        if free_marker not in api:
            raise RuntimeError("dynamic stream association: EngineAPI unload marker missing")
        api = api.replace(free_marker, free_new, 1)
    api_path.write_text(api, encoding="utf-8")

    vk = vk_path.read_text(encoding="utf-8")
    state_marker = "    VkDeviceSize g_stream_index_capacity = 0;\n"
    state_block = state_marker + '''    IDirect3DVertexBuffer9* g_stream_vertex_source = NULL;
    u32 g_stream_vertex_discard_id = 0;
    VkDeviceSize g_stream_vertex_valid_begin = 0;
    VkDeviceSize g_stream_vertex_valid_end = 0;
    IDirect3DIndexBuffer9* g_stream_index_source = NULL;
    u32 g_stream_index_discard_id = 0;
    VkDeviceSize g_stream_index_valid_begin = 0;
    VkDeviceSize g_stream_index_valid_end = 0;
'''
    if "g_stream_vertex_source" not in vk:
        if state_marker not in vk:
            raise RuntimeError("dynamic stream association: Vulkan stream state marker missing")
        vk = vk.replace(state_marker, state_block, 1)

    export_marker = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'
    exports = r'''extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_vertex_stream_upload(
    IDirect3DVertexBuffer9* source, const void* data, u32 byte_count, u32 byte_offset, u32 discard_id)
{
    if (!source || !data || !byte_count || !xr_vk_bootstrap_runtime_ready())
        return FALSE;
    if (!xr_vk_upload_vertex_stream(data, byte_count, byte_offset))
        return FALSE;
    if (g_stream_vertex_source != source || g_stream_vertex_discard_id != discard_id)
    {
        g_stream_vertex_source = source;
        g_stream_vertex_discard_id = discard_id;
        g_stream_vertex_valid_begin = byte_offset;
        g_stream_vertex_valid_end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
    }
    else
    {
        if (byte_offset < g_stream_vertex_valid_begin) g_stream_vertex_valid_begin = byte_offset;
        const VkDeviceSize end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
        if (end > g_stream_vertex_valid_end) g_stream_vertex_valid_end = end;
    }
    return TRUE;
}

extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_index_stream_upload(
    IDirect3DIndexBuffer9* source, const void* data, u32 byte_count, u32 byte_offset, u32 discard_id)
{
    if (!source || !data || !byte_count || !xr_vk_bootstrap_runtime_ready())
        return FALSE;
    if (!xr_vk_upload_index_stream(data, byte_count, byte_offset))
        return FALSE;
    if (g_stream_index_source != source || g_stream_index_discard_id != discard_id)
    {
        g_stream_index_source = source;
        g_stream_index_discard_id = discard_id;
        g_stream_index_valid_begin = byte_offset;
        g_stream_index_valid_end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
    }
    else
    {
        if (byte_offset < g_stream_index_valid_begin) g_stream_index_valid_begin = byte_offset;
        const VkDeviceSize end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
        if (end > g_stream_index_valid_end) g_stream_index_valid_end = end;
    }
    return TRUE;
}

    bool xr_vk_dynamic_vertex_range_ready(IDirect3DVertexBuffer9* source, u32 first_vertex,
        u32 vertex_count, u32 stride, VkDeviceSize& vertex_offset)
    {
        if (!source || source != g_stream_vertex_source || !vertex_count || !stride)
            return false;
        const VkDeviceSize begin = static_cast<VkDeviceSize>(first_vertex) * stride;
        const VkDeviceSize end = begin + static_cast<VkDeviceSize>(vertex_count) * stride;
        if (end < begin || begin < g_stream_vertex_valid_begin || end > g_stream_vertex_valid_end)
            return false;
        vertex_offset = begin;
        return true;
    }

    bool xr_vk_dynamic_index_range_ready(IDirect3DIndexBuffer9* source, u32 first_index,
        u32 index_count, VkDeviceSize& index_offset)
    {
        if (!source || source != g_stream_index_source || !index_count)
            return false;
        const VkDeviceSize begin = static_cast<VkDeviceSize>(first_index) * sizeof(u16);
        const VkDeviceSize end = begin + static_cast<VkDeviceSize>(index_count) * sizeof(u16);
        if (end < begin || begin < g_stream_index_valid_begin || end > g_stream_index_valid_end)
            return false;
        index_offset = 0;
        return true;
    }

'''
    if "xrRender_vk_vertex_stream_upload" not in vk:
        pos = vk.find(export_marker)
        if pos < 0:
            raise RuntimeError("dynamic stream association: backend export marker missing")
        vk = vk[:pos] + exports + vk[pos:]

    destroy_start = vk.find("void xr_vk_destroy_frame_resources()")
    destroy_end = vk.find("void xr_vk_destroy_window_runtime()", destroy_start)
    if destroy_start < 0 or destroy_end < 0:
        raise RuntimeError("dynamic stream association: Vulkan destroy functions missing")
    destroy = vk[destroy_start:destroy_end]
    reset_marker = "        g_stream_index_capacity = 0;\n"
    reset = reset_marker + '''        g_stream_vertex_source = NULL;
        g_stream_vertex_discard_id = 0;
        g_stream_vertex_valid_begin = g_stream_vertex_valid_end = 0;
        g_stream_index_source = NULL;
        g_stream_index_discard_id = 0;
        g_stream_index_valid_begin = g_stream_index_valid_end = 0;
'''
    if "g_stream_vertex_source = NULL;" not in destroy:
        if reset_marker not in destroy:
            # Stream buffer helper may reset capacity indirectly; append before the function closes.
            close = destroy.rfind("    }\n")
            if close < 0:
                raise RuntimeError("dynamic stream association: destroy close marker missing")
            destroy = destroy[:close] + '''        g_stream_vertex_source = NULL;
        g_stream_vertex_discard_id = 0;
        g_stream_vertex_valid_begin = g_stream_vertex_valid_end = 0;
        g_stream_index_source = NULL;
        g_stream_index_discard_id = 0;
        g_stream_index_valid_begin = g_stream_index_valid_end = 0;
''' + destroy[close:]
        else:
            destroy = destroy.replace(reset_marker, reset, 1)
        vk = vk[:destroy_start] + destroy + vk[destroy_end:]

    vk_path.write_text(vk, encoding="utf-8")

    final_h = ds_h.read_text(encoding="utf-8")
    final_cpp = ds_cpp.read_text(encoding="utf-8")
    final_api = api_path.read_text(encoding="utf-8")
    final_vk = vk_path.read_text(encoding="utf-8")
    required = (
        (final_h, "xr_vk_vertex_stream_upload_fn"),
        (final_h, "void* vkLockData;"),
        (final_cpp, "g_xr_vk_vertex_stream_upload(pVB, vkLockData"),
        (final_cpp, "g_xr_vk_index_stream_upload(pIB, vkLockData"),
        (final_api, 'GetProcAddress(hRender, "xrRender_vk_vertex_stream_upload")'),
        (final_vk, "g_stream_vertex_source"),
        (final_vk, "xr_vk_dynamic_vertex_range_ready"),
        (final_vk, "xr_vk_dynamic_index_range_ready"),
    )
    for haystack, token in required:
        if token not in haystack:
            raise RuntimeError(f"dynamic stream association validation failed: missing {token}")

    print("[vulkan-dynamic-stream-association] D3D9 WRITEONLY dynamic VB/IB mirrored at Unlock with source/range identity")


def main() -> int:
    parser = argparse.ArgumentParser(description="Associate SHOC dynamic D3D9 stream writes with Vulkan mirror ranges safely at Unlock.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
