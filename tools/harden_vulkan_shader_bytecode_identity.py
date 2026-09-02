from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    helper_marker = "    VkShaderModule xr_vk_create_shader_module(const void* data, size_t size)\n"
    helpers = r'''    u64 xr_vk_hash_shader_bytecode(const void* data, u32 size)
    {
        if (!data || !size)
            return 0;
        const u8* bytes = static_cast<const u8*>(data);
        u64 hash = 1469598103934665603ull;
        for (u32 i = 0; i < size; ++i)
        {
            hash ^= static_cast<u64>(bytes[i]);
            hash *= 1099511628211ull;
        }
        return hash ? hash : 1ull;
    }

    bool xr_vk_vertex_shader_bytecode_identity(IDirect3DVertexShader9* shader, u64& identity)
    {
        identity = 0;
        if (!shader)
            return false;
        UINT size = 0;
        if (FAILED(shader->GetFunction(NULL, &size)) || !size)
            return false;
        xr_vector<u8> bytecode(size);
        UINT actual_size = size;
        if (FAILED(shader->GetFunction(&bytecode[0], &actual_size)) || !actual_size || actual_size > size)
            return false;
        identity = xr_vk_hash_shader_bytecode(&bytecode[0], static_cast<u32>(actual_size));
        return identity != 0;
    }

    bool xr_vk_pixel_shader_bytecode_identity(IDirect3DPixelShader9* shader, u64& identity)
    {
        identity = 0;
        if (!shader)
            return false;
        UINT size = 0;
        if (FAILED(shader->GetFunction(NULL, &size)) || !size)
            return false;
        xr_vector<u8> bytecode(size);
        UINT actual_size = size;
        if (FAILED(shader->GetFunction(&bytecode[0], &actual_size)) || !actual_size || actual_size > size)
            return false;
        identity = xr_vk_hash_shader_bytecode(&bytecode[0], static_cast<u32>(actual_size));
        return identity != 0;
    }

'''
    if "xr_vk_hash_shader_bytecode" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan shader bytecode identity: shader-module helper marker not found")
        text = text.replace(helper_marker, helpers + helper_marker, 1)

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan shader bytecode identity: renderer exports not found")

    indexed = text[indexed_start:plain_start]
    command_guard = '''    if (command_buffer == VK_NULL_HANDLE)
        return FALSE;'''
    identity_block = r'''

    u64 vertex_shader_identity = 0;
    u64 pixel_shader_identity = 0;
    if (!xr_vk_vertex_shader_bytecode_identity(vertex_shader, vertex_shader_identity) ||
        !xr_vk_pixel_shader_bytecode_identity(pixel_shader, pixel_shader_identity))
        return FALSE;'''
    if "vertex_shader_identity = 0" not in indexed:
        if command_guard not in indexed:
            raise RuntimeError("Vulkan shader bytecode identity: indexed active-command guard not found")
        indexed = indexed.replace(command_guard, command_guard + identity_block, 1)
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    plain = text[plain_start:]
    if "vertex_shader_identity = 0" not in plain:
        if command_guard not in plain:
            raise RuntimeError("Vulkan shader bytecode identity: plain active-command guard not found")
        plain = plain.replace(command_guard, command_guard + identity_block, 1)
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "u64 xr_vk_hash_shader_bytecode",
        "1469598103934665603ull",
        "1099511628211ull",
        "shader->GetFunction(NULL, &size)",
        "shader->GetFunction(&bytecode[0], &actual_size)",
        "xr_vk_vertex_shader_bytecode_identity",
        "xr_vk_pixel_shader_bytecode_identity",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan shader bytecode identity validation failed: missing {token}")

    indexed_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    for label, block in (("indexed", final[indexed_start:plain_start]), ("plain", final[plain_start:])):
        for token in (
            "u64 vertex_shader_identity = 0;",
            "u64 pixel_shader_identity = 0;",
            "xr_vk_vertex_shader_bytecode_identity(vertex_shader, vertex_shader_identity)",
            "xr_vk_pixel_shader_bytecode_identity(pixel_shader, pixel_shader_identity)",
        ):
            if token not in block:
                raise RuntimeError(f"Vulkan shader bytecode identity validation failed in {label} export: missing {token}")
        active = block.find("xr_vk_bootstrap_active_command_buffer()")
        identity = block.find("xr_vk_vertex_shader_bytecode_identity")
        fallback = block.rfind("return FALSE;")
        if min(active, identity, fallback) < 0 or not active < identity < fallback:
            raise RuntimeError(f"Vulkan shader bytecode identity validation failed in {label} export: guard order invalid")

    print("[vulkan-shader-identity] stable FNV-1a identities derived from live D3D9 VS/PS bytecode after active-frame gating")


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive deterministic Vulkan shader identities from the live D3D9 shader bytecode.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
