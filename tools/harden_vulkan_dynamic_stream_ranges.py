from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    vertex_old = '''    else
    {
        if (byte_offset < g_stream_vertex_valid_begin) g_stream_vertex_valid_begin = byte_offset;
        const VkDeviceSize end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
        if (end > g_stream_vertex_valid_end) g_stream_vertex_valid_end = end;
    }
'''
    vertex_new = '''    else
    {
        const VkDeviceSize begin = byte_offset;
        const VkDeviceSize end = begin + byte_count;
        if (begin > g_stream_vertex_valid_end || end < g_stream_vertex_valid_begin)
        {
            // A gap would make untouched WRITEONLY D3D bytes look valid in the Vulkan mirror.
            // Start a new exact interval instead of merging disjoint uploads.
            g_stream_vertex_valid_begin = begin;
            g_stream_vertex_valid_end = end;
        }
        else
        {
            if (begin < g_stream_vertex_valid_begin) g_stream_vertex_valid_begin = begin;
            if (end > g_stream_vertex_valid_end) g_stream_vertex_valid_end = end;
        }
    }
'''
    if "begin > g_stream_vertex_valid_end || end < g_stream_vertex_valid_begin" not in text:
        if vertex_old not in text:
            raise RuntimeError("dynamic stream range hardening: vertex merge marker missing")
        text = text.replace(vertex_old, vertex_new, 1)

    index_old = '''    else
    {
        if (byte_offset < g_stream_index_valid_begin) g_stream_index_valid_begin = byte_offset;
        const VkDeviceSize end = static_cast<VkDeviceSize>(byte_offset) + byte_count;
        if (end > g_stream_index_valid_end) g_stream_index_valid_end = end;
    }
'''
    index_new = '''    else
    {
        const VkDeviceSize begin = byte_offset;
        const VkDeviceSize end = begin + byte_count;
        if (begin > g_stream_index_valid_end || end < g_stream_index_valid_begin)
        {
            g_stream_index_valid_begin = begin;
            g_stream_index_valid_end = end;
        }
        else
        {
            if (begin < g_stream_index_valid_begin) g_stream_index_valid_begin = begin;
            if (end > g_stream_index_valid_end) g_stream_index_valid_end = end;
        }
    }
'''
    if "begin > g_stream_index_valid_end || end < g_stream_index_valid_begin" not in text:
        if index_old not in text:
            raise RuntimeError("dynamic stream range hardening: index merge marker missing")
        text = text.replace(index_old, index_new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    for token in (
        "begin > g_stream_vertex_valid_end || end < g_stream_vertex_valid_begin",
        "g_stream_vertex_valid_begin = begin;",
        "g_stream_vertex_valid_end = end;",
        "begin > g_stream_index_valid_end || end < g_stream_index_valid_begin",
        "g_stream_index_valid_begin = begin;",
        "g_stream_index_valid_end = end;",
    ):
        if token not in final:
            raise RuntimeError(f"dynamic stream range hardening validation failed: missing {token}")

    print("[vulkan-dynamic-stream-ranges] disjoint WRITEONLY uploads no longer create falsely valid mirror gaps")


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Vulkan dynamic stream mirror validity intervals gap-safe.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
