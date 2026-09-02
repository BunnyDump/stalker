from __future__ import annotations

import argparse
from pathlib import Path

from harden_vulkan_backend_stateblock_identity import harden as harden_vulkan_backend_stateblock_identity
from harden_vulkan_backend_render_state_bridge import harden as harden_vulkan_backend_render_state_bridge


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    old_loop = r'''        u64 hash = 1469598103934665603ull;
        for (UINT i = 0; i < actual_count; ++i)
        {
            const D3DVERTEXELEMENT9& element = elements[i];
            const u32 fields[] = {
                static_cast<u32>(element.Stream), static_cast<u32>(element.Offset),
                static_cast<u32>(element.Type), static_cast<u32>(element.Method),
                static_cast<u32>(element.Usage), static_cast<u32>(element.UsageIndex)
            };
            for (u32 field = 0; field < sizeof(fields) / sizeof(fields[0]); ++field)
            {
                u32 value = fields[field];
                for (u32 byte_index = 0; byte_index < sizeof(value); ++byte_index)
                {
                    hash ^= static_cast<u64>(value & 0xffu);
                    hash *= 1099511628211ull;
                    value >>= 8;
                }
            }
        }
        identity = hash ? hash : 1ull;
        return true;
'''
    canonical_without_count = r'''        u64 hash = 1469598103934665603ull;
        bool terminated = false;
        for (UINT i = 0; i < actual_count; ++i)
        {
            const D3DVERTEXELEMENT9& element = elements[i];
            if (element.Stream == 0xff && element.Type == D3DDECLTYPE_UNUSED)
            {
                terminated = true;
                break;
            }
            const u32 fields[] = {
                static_cast<u32>(element.Stream), static_cast<u32>(element.Offset),
                static_cast<u32>(element.Type), static_cast<u32>(element.Method),
                static_cast<u32>(element.Usage), static_cast<u32>(element.UsageIndex)
            };
            for (u32 field = 0; field < sizeof(fields) / sizeof(fields[0]); ++field)
            {
                u32 value = fields[field];
                for (u32 byte_index = 0; byte_index < sizeof(value); ++byte_index)
                {
                    hash ^= static_cast<u64>(value & 0xffu);
                    hash *= 1099511628211ull;
                    value >>= 8;
                }
            }
        }
        if (!terminated)
            return false;
        identity = hash ? hash : 1ull;
        return true;
'''
    new_loop = r'''        u64 hash = 1469598103934665603ull;
        bool terminated = false;
        u32 semantic_element_count = 0;
        for (UINT i = 0; i < actual_count; ++i)
        {
            const D3DVERTEXELEMENT9& element = elements[i];
            if (element.Stream == 0xff && element.Type == D3DDECLTYPE_UNUSED)
            {
                terminated = true;
                break;
            }
            const u32 fields[] = {
                static_cast<u32>(element.Stream), static_cast<u32>(element.Offset),
                static_cast<u32>(element.Type), static_cast<u32>(element.Method),
                static_cast<u32>(element.Usage), static_cast<u32>(element.UsageIndex)
            };
            for (u32 field = 0; field < sizeof(fields) / sizeof(fields[0]); ++field)
            {
                u32 value = fields[field];
                for (u32 byte_index = 0; byte_index < sizeof(value); ++byte_index)
                {
                    hash ^= static_cast<u64>(value & 0xffu);
                    hash *= 1099511628211ull;
                    value >>= 8;
                }
            }
            ++semantic_element_count;
        }
        if (!terminated || !semantic_element_count)
            return false;
        identity = hash ? hash : 1ull;
        return true;
'''

    if "u32 semantic_element_count = 0;" not in text:
        if canonical_without_count in text:
            text = text.replace(canonical_without_count, new_loop, 1)
        elif old_loop in text:
            text = text.replace(old_loop, new_loop, 1)
        else:
            raise RuntimeError("Vulkan backend pipeline key semantics: declaration hash loop marker not found")

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")

    required = (
        "u32 semantic_element_count = 0;",
        "element.Stream == 0xff && element.Type == D3DDECLTYPE_UNUSED",
        "terminated = true;",
        "++semantic_element_count;",
        "if (!terminated || !semantic_element_count)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan backend pipeline key semantics validation failed: missing {token}")

    start = final.find("bool xr_vk_vertex_declaration_identity")
    end = final.find("bool xr_vk_backend_pipeline_key_equal", start)
    if start < 0 or end < 0:
        raise RuntimeError("Vulkan backend pipeline key semantics validation failed: helper boundaries missing")
    block = final[start:end]
    terminator = block.find("element.Stream == 0xff && element.Type == D3DDECLTYPE_UNUSED")
    fields = block.find("const u32 fields[]")
    if terminator < 0 or fields < 0 or terminator > fields:
        raise RuntimeError("Vulkan backend pipeline key semantics validation failed: terminator is hashed as semantic state")

    harden_vulkan_backend_stateblock_identity(root)
    harden_vulkan_backend_render_state_bridge(root)

    print("[vulkan-backend-pipeline-key] idempotent semantic declaration hash + canonical D3D9 render-state identity isolation installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Vulkan backend pipeline keys with semantic declarations and canonical D3D9 render-state identity.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
