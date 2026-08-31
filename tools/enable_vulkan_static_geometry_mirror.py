from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    root = root.resolve()
    renderer = root / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    loader = renderer / "r2_loader.cpp"
    visual = root / "xr_3da" / "xrRender" / "FVisual.cpp"
    for path in (source, loader, visual):
        if not path.is_file():
            raise FileNotFoundError(path)

    text = source.read_text(encoding="utf-8")
    marker = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'
    if marker not in text:
        raise RuntimeError("Vulkan static geometry mirror: backend export marker not found")

    block = r'''    struct xr_vk_static_geometry_mirror
    {
        const void* source;
        VkBuffer buffer;
        VkDeviceMemory memory;
        VkDeviceSize size;
        D3DFORMAT index_format;
        bool index_buffer;
    };

    xr_vector<xr_vk_static_geometry_mirror> g_static_geometry_mirrors;

    xr_vk_static_geometry_mirror* xr_vk_find_static_geometry_mirror(const void* source, bool index_buffer)
    {
        if (!source)
            return NULL;
        for (u32 i = 0; i < g_static_geometry_mirrors.size(); ++i)
            if (g_static_geometry_mirrors[i].source == source &&
                g_static_geometry_mirrors[i].index_buffer == index_buffer)
                return &g_static_geometry_mirrors[i];
        return NULL;
    }

    void xr_vk_destroy_static_geometry_mirror(xr_vk_static_geometry_mirror& mirror)
    {
        if (g_device != VK_NULL_HANDLE)
        {
            if (mirror.buffer != VK_NULL_HANDLE && g_vkDestroyBuffer)
                g_vkDestroyBuffer(g_device, mirror.buffer, NULL);
            if (mirror.memory != VK_NULL_HANDLE && g_vkFreeMemory)
                g_vkFreeMemory(g_device, mirror.memory, NULL);
        }
        mirror.buffer = VK_NULL_HANDLE;
        mirror.memory = VK_NULL_HANDLE;
        mirror.size = 0;
        mirror.source = NULL;
    }

    bool xr_vk_register_static_geometry_mirror(const void* source, const void* data, VkDeviceSize size,
        bool index_buffer, D3DFORMAT index_format)
    {
        if (!source || !data || !size || g_device == VK_NULL_HANDLE || !g_vkMapMemory || !g_vkUnmapMemory)
            return false;
        if (g_frame_submission_pending && !xr_vk_wait_for_stream_write_safety())
            return false;

        xr_vk_static_geometry_mirror* existing = xr_vk_find_static_geometry_mirror(source, index_buffer);
        if (existing)
            xr_vk_destroy_static_geometry_mirror(*existing);

        xr_vk_static_geometry_mirror mirror = {};
        mirror.source = source;
        mirror.size = size;
        mirror.index_format = index_format;
        mirror.index_buffer = index_buffer;
        const VkBufferUsageFlags usage = index_buffer ? VK_BUFFER_USAGE_INDEX_BUFFER_BIT : VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
        if (!xr_vk_create_buffer(size, usage,
                VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
                mirror.buffer, mirror.memory))
            return false;

        void* mapped = NULL;
        if (g_vkMapMemory(g_device, mirror.memory, 0, size, 0, &mapped) != VK_SUCCESS || !mapped)
        {
            xr_vk_destroy_static_geometry_mirror(mirror);
            return false;
        }
        CopyMemory(mapped, data, static_cast<SIZE_T>(size));
        g_vkUnmapMemory(g_device, mirror.memory);

        if (existing)
            *existing = mirror;
        else
            g_static_geometry_mirrors.push_back(mirror);
        return true;
    }

    void xr_vk_clear_static_geometry_mirrors()
    {
        if (g_device != VK_NULL_HANDLE && g_vkDeviceWaitIdle)
            g_vkDeviceWaitIdle(g_device);
        for (u32 i = 0; i < g_static_geometry_mirrors.size(); ++i)
            xr_vk_destroy_static_geometry_mirror(g_static_geometry_mirrors[i]);
        g_static_geometry_mirrors.clear();
    }

    extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_vertex_buffer(
        IDirect3DVertexBuffer9* source, const void* data, u32 size)
    {
        return xr_vk_register_static_geometry_mirror(source, data, size, false, D3DFMT_UNKNOWN) ? TRUE : FALSE;
    }

    extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_register_static_index_buffer(
        IDirect3DIndexBuffer9* source, const void* data, u32 size, D3DFORMAT format)
    {
        if (format != D3DFMT_INDEX16 && format != D3DFMT_INDEX32)
            return FALSE;
        return xr_vk_register_static_geometry_mirror(source, data, size, true, format) ? TRUE : FALSE;
    }

    extern "C" __declspec(dllexport) void __cdecl xrRender_vk_clear_static_geometry()
    {
        xr_vk_clear_static_geometry_mirrors();
    }

    bool xr_vk_record_static_indexed_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,
        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer,
        IDirect3DIndexBuffer9* index_buffer, u32 vertex_stride, u32 base_vertex,
        u32 start_vertex, u32 vertex_count, u32 start_index, u32 primitive_count)
    {
        xr_vk_static_geometry_mirror* vb = xr_vk_find_static_geometry_mirror(vertex_buffer, false);
        xr_vk_static_geometry_mirror* ib = xr_vk_find_static_geometry_mirror(index_buffer, true);
        if (!vb || !ib || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_stride ||
            !g_vkCmdBindVertexBuffers || !g_vkCmdBindIndexBuffer || !g_vkCmdBindPipeline || !g_vkCmdDrawIndexed)
            return false;

        u32 index_count = 0;
        if (!xr_vk_primitive_element_count(primitive, primitive_count, index_count) || !index_count)
            return false;
        const u32 index_stride = ib->index_format == D3DFMT_INDEX32 ? 4u : 2u;
        const VkIndexType index_type = ib->index_format == D3DFMT_INDEX32 ? VK_INDEX_TYPE_UINT32 : VK_INDEX_TYPE_UINT16;
        const VkDeviceSize required_vertices = static_cast<VkDeviceSize>(base_vertex) + start_vertex + vertex_count;
        const VkDeviceSize required_vertex_bytes = required_vertices * vertex_stride;
        const VkDeviceSize index_offset = static_cast<VkDeviceSize>(start_index) * index_stride;
        const VkDeviceSize required_index_bytes = index_offset + static_cast<VkDeviceSize>(index_count) * index_stride;
        if (required_vertex_bytes > vb->size || required_index_bytes > ib->size || base_vertex > 0x7fffffffu)
            return false;

        const VkDeviceSize vertex_offset = 0;
        g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vb->buffer, &vertex_offset);
        g_vkCmdBindIndexBuffer(command_buffer, ib->buffer, index_offset, index_type);
        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        g_vkCmdDrawIndexed(command_buffer, index_count, 1, 0, static_cast<s32>(base_vertex), 0);
        return true;
    }

    bool xr_vk_record_static_backend_draw(VkCommandBuffer command_buffer, VkPipeline pipeline,
        D3DPRIMITIVETYPE primitive, IDirect3DVertexBuffer9* vertex_buffer, u32 vertex_stride,
        u32 start_vertex, u32 primitive_count)
    {
        xr_vk_static_geometry_mirror* vb = xr_vk_find_static_geometry_mirror(vertex_buffer, false);
        if (!vb || command_buffer == VK_NULL_HANDLE || pipeline == VK_NULL_HANDLE || !vertex_stride ||
            !g_vkCmdBindVertexBuffers || !g_vkCmdBindPipeline || !g_vkCmdDraw)
            return false;
        u32 vertex_count = 0;
        if (!xr_vk_primitive_element_count(primitive, primitive_count, vertex_count) || !vertex_count)
            return false;
        const VkDeviceSize required_vertex_bytes = static_cast<VkDeviceSize>(start_vertex + vertex_count) * vertex_stride;
        if (required_vertex_bytes > vb->size)
            return false;
        const VkDeviceSize vertex_offset = 0;
        g_vkCmdBindVertexBuffers(command_buffer, 0, 1, &vb->buffer, &vertex_offset);
        g_vkCmdBindPipeline(command_buffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0);
        return true;
    }

'''
    if "xrRender_vk_register_static_vertex_buffer" not in text:
        text = text.replace(marker, block + marker, 1)
    source.write_text(text, encoding="utf-8")

    # Shared model loader: resolve Vulkan exports dynamically, so R1/R2 binaries remain unaffected.
    v = visual.read_text(encoding="utf-8")
    helper_marker = '#include "fvisual.h"\n'
    helper = r'''

typedef BOOL (__cdecl *xr_vk_register_static_vb_fn)(IDirect3DVertexBuffer9*, const void*, u32);
typedef BOOL (__cdecl *xr_vk_register_static_ib_fn)(IDirect3DIndexBuffer9*, const void*, u32, D3DFORMAT);
static void xr_vk_try_register_static_vb(IDirect3DVertexBuffer9* vb, const void* data, u32 size)
{
    HMODULE module = GetModuleHandleA("xrRender_VK.dll");
    xr_vk_register_static_vb_fn fn = module ? reinterpret_cast<xr_vk_register_static_vb_fn>(GetProcAddress(module, "xrRender_vk_register_static_vertex_buffer")) : NULL;
    if (fn) fn(vb, data, size);
}
static void xr_vk_try_register_static_ib(IDirect3DIndexBuffer9* ib, const void* data, u32 size, D3DFORMAT format)
{
    HMODULE module = GetModuleHandleA("xrRender_VK.dll");
    xr_vk_register_static_ib_fn fn = module ? reinterpret_cast<xr_vk_register_static_ib_fn>(GetProcAddress(module, "xrRender_vk_register_static_index_buffer")) : NULL;
    if (fn) fn(ib, data, size, format);
}
'''
    if "xr_vk_try_register_static_vb" not in v:
        if helper_marker not in v:
            raise RuntimeError("Vulkan static geometry mirror: FVisual include marker not found")
        v = v.replace(helper_marker, helper_marker + helper, 1)
        vb_unlock = "\t\t\tCopyMemory(bytes, data->pointer(), vCount * vStride);\n\t\t\tp_rm_Vertices->Unlock();"
        ib_unlock = "\t\t\tCopyMemory(bytes, data->pointer(), iCount * 2);\n\t\t\tp_rm_Indices->Unlock();"
        if vb_unlock not in v or ib_unlock not in v:
            raise RuntimeError("Vulkan static geometry mirror: FVisual upload markers not found")
        v = v.replace(vb_unlock, "\t\t\tCopyMemory(bytes, data->pointer(), vCount * vStride);\n\t\t\txr_vk_try_register_static_vb(p_rm_Vertices, bytes, vCount * vStride);\n\t\t\tp_rm_Vertices->Unlock();", 1)
        v = v.replace(ib_unlock, "\t\t\tCopyMemory(bytes, data->pointer(), iCount * 2);\n\t\t\txr_vk_try_register_static_ib(p_rm_Indices, bytes, iCount * 2, D3DFMT_INDEX16);\n\t\t\tp_rm_Indices->Unlock();", 1)
        visual.write_text(v, encoding="utf-8")

    l = loader.read_text(encoding="utf-8")
    include_marker = '#include "../xrCore/stream_reader.h"\n'
    loader_helpers = r'''

typedef BOOL (__cdecl *xr_vk_register_level_vb_fn)(IDirect3DVertexBuffer9*, const void*, u32);
typedef BOOL (__cdecl *xr_vk_register_level_ib_fn)(IDirect3DIndexBuffer9*, const void*, u32, D3DFORMAT);
typedef void (__cdecl *xr_vk_clear_static_geometry_fn)();
static HMODULE xr_vk_renderer_module() { return GetModuleHandleA("xrRender_VK.dll"); }
static void xr_vk_register_level_vb(IDirect3DVertexBuffer9* vb, const void* data, u32 size)
{
    HMODULE m = xr_vk_renderer_module();
    xr_vk_register_level_vb_fn fn = m ? reinterpret_cast<xr_vk_register_level_vb_fn>(GetProcAddress(m, "xrRender_vk_register_static_vertex_buffer")) : NULL;
    if (fn) fn(vb, data, size);
}
static void xr_vk_register_level_ib(IDirect3DIndexBuffer9* ib, const void* data, u32 size)
{
    HMODULE m = xr_vk_renderer_module();
    xr_vk_register_level_ib_fn fn = m ? reinterpret_cast<xr_vk_register_level_ib_fn>(GetProcAddress(m, "xrRender_vk_register_static_index_buffer")) : NULL;
    if (fn) fn(ib, data, size, D3DFMT_INDEX16);
}
static void xr_vk_clear_level_geometry()
{
    HMODULE m = xr_vk_renderer_module();
    xr_vk_clear_static_geometry_fn fn = m ? reinterpret_cast<xr_vk_clear_static_geometry_fn>(GetProcAddress(m, "xrRender_vk_clear_static_geometry")) : NULL;
    if (fn) fn();
}
'''
    if "xr_vk_register_level_vb" not in l:
        if include_marker not in l:
            raise RuntimeError("Vulkan static geometry mirror: r2_loader include marker not found")
        l = l.replace(include_marker, include_marker + loader_helpers, 1)
        vb_unlock = "\t\t\tfs->r(pData, vCount * vSize);\n\t\t\t_VB[i]->Unlock();"
        ib_unlock = "\t\t\tfs->r(pData, iCount * 2);\n\t\t\t_IB[i]->Unlock();"
        if vb_unlock not in l or ib_unlock not in l:
            raise RuntimeError("Vulkan static geometry mirror: level upload markers not found")
        l = l.replace(vb_unlock, "\t\t\tfs->r(pData, vCount * vSize);\n\t\t\txr_vk_register_level_vb(_VB[i], pData, vCount * vSize);\n\t\t\t_VB[i]->Unlock();", 1)
        l = l.replace(ib_unlock, "\t\t\tfs->r(pData, iCount * 2);\n\t\t\txr_vk_register_level_ib(_IB[i], pData, iCount * 2);\n\t\t\t_IB[i]->Unlock();", 1)
        release_marker = "\t//*** VB/IB\n"
        if release_marker not in l:
            raise RuntimeError("Vulkan static geometry mirror: level unload marker not found")
        l = l.replace(release_marker, "\txr_vk_clear_level_geometry();\n\n" + release_marker, 1)
        loader.write_text(l, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    for token in (
        "g_static_geometry_mirrors", "xrRender_vk_register_static_vertex_buffer",
        "xrRender_vk_register_static_index_buffer", "xrRender_vk_clear_static_geometry",
        "xr_vk_record_static_indexed_backend_draw", "xr_vk_record_static_backend_draw",
        "VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT",
    ):
        if token not in final:
            raise RuntimeError(f"Vulkan static geometry mirror validation failed: missing {token}")
    print("[vulkan-static-geometry] level.geom/geomx + standalone OGF immutable VB/IB mirrors installed with D3D-safe dynamic export lookup")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror SHOC static level/model geometry into Vulkan buffers at load time.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
