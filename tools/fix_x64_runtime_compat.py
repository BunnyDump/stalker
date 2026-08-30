from __future__ import annotations

import argparse
from pathlib import Path

from enable_vulkan_bootstrap import enable_vulkan_bootstrap
from enable_vulkan_capability_probe import enable_vulkan_capability_probe
from harden_vulkan_capability_probe import harden as harden_vulkan_capability_probe
from harden_vulkan_shader_pipeline_cache import harden as harden_vulkan_shader_pipeline_cache

JIT_GUARD_OLD = b"#ifdef USE_JIT"
JIT_GUARD_NEW = b"#if defined(USE_JIT) && !defined(_WIN64)"

ISPATIAL_EMPTY_OLD = b'''\tBOOL _empty()\n\t{\n\t\treturn items.empty() && (0 == (ptrt(children[0]) | ptrt(children[1]) | ptrt(children[2]) | ptrt(children[3]) |\n\t\t\t\t\t\t\t\t\t   ptrt(children[4]) | ptrt(children[5]) | ptrt(children[6]) | ptrt(children[7])));\n\t}'''
ISPATIAL_EMPTY_NEW = b'''\tBOOL _empty()\n\t{\n\t\treturn items.empty() && children[0] == 0 && children[1] == 0 && children[2] == 0 && children[3] == 0 &&\n\t\t\tchildren[4] == 0 && children[5] == 0 && children[6] == 0 && children[7] == 0;\n\t}'''

STREAM_TELL_OLD = b'''IC u32 CStreamReader::tell() const\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tVERIFY(u32(m_current_pointer - m_start_pointer) <= m_current_window_size);\n\treturn (m_current_offset_from_start + (m_current_pointer - m_start_pointer));\n}'''
STREAM_TELL_NEW = b'''IC u32 CStreamReader::tell() const\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tconst size_t window_offset = size_t(m_current_pointer - m_start_pointer);\n\tVERIFY(window_offset <= m_current_window_size);\n\treturn (m_current_offset_from_start + u32(window_offset));\n}'''

STREAM_ADVANCE_OLD = b'''void CStreamReader::advance(const int& offset)\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tVERIFY(u32(m_current_pointer - m_start_pointer) <= m_current_window_size);\n\tint offset_inside_window = int(m_current_pointer - m_start_pointer);\n\tif (offset_inside_window + offset >= (int)m_current_window_size)\n\t{\n\t\tremap(m_current_offset_from_start + offset_inside_window + offset);\n\t\treturn;\n\t}\n\n\tif (offset_inside_window + offset < 0)\n\t{\n\t\tremap(m_current_offset_from_start + offset_inside_window + offset);\n\t\treturn;\n\t}\n\n\tm_current_pointer += offset;\n}'''
STREAM_ADVANCE_NEW = b'''void CStreamReader::advance(const int& offset)\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tconst s64 offset_inside_window = s64(m_current_pointer - m_start_pointer);\n\tVERIFY(offset_inside_window >= 0);\n\tVERIFY(u64(offset_inside_window) <= m_current_window_size);\n\n\tconst s64 target_offset = offset_inside_window + s64(offset);\n\tif (target_offset >= s64(m_current_window_size) || target_offset < 0)\n\t{\n\t\tconst s64 absolute_offset = s64(m_current_offset_from_start) + target_offset;\n\t\tVERIFY(absolute_offset >= 0);\n\t\tVERIFY(u64(absolute_offset) <= m_file_size);\n\t\tremap(u32(absolute_offset));\n\t\treturn;\n\t}\n\n\tm_current_pointer += offset;\n}'''

STREAM_READ_OLD = b'''void CStreamReader::r(void* _buffer, u32 buffer_size)\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tVERIFY(u32(m_current_pointer - m_start_pointer) <= m_current_window_size);\n\n\tint offset_inside_window = int(m_current_pointer - m_start_pointer);\n\tif (offset_inside_window + buffer_size < m_current_window_size)\n\t{\n\t\tMemory.mem_copy(_buffer, m_current_pointer, buffer_size);\n\t\tm_current_pointer += buffer_size;\n\t\treturn;\n\t}\n\n\tu8* buffer = (u8*)_buffer;\n\tu32 elapsed_in_window = m_current_window_size - (m_current_pointer - m_start_pointer);\n\n\tdo\n\t{\n\t\tMemory.mem_copy(buffer, m_current_pointer, elapsed_in_window);\n\t\tbuffer += elapsed_in_window;\n\t\tbuffer_size -= elapsed_in_window;\n\t\tadvance(elapsed_in_window);\n\n\t\telapsed_in_window = m_current_window_size;\n\t} while (m_current_window_size < buffer_size);\n\n\tMemory.mem_copy(buffer, m_current_pointer, buffer_size);\n\tadvance(buffer_size);\n}'''
STREAM_READ_NEW = b'''void CStreamReader::r(void* _buffer, u32 buffer_size)\n{\n\tVERIFY(m_current_pointer >= m_start_pointer);\n\tconst size_t offset_inside_window = size_t(m_current_pointer - m_start_pointer);\n\tVERIFY(offset_inside_window <= m_current_window_size);\n\n\tif (offset_inside_window + buffer_size < m_current_window_size)\n\t{\n\t\tMemory.mem_copy(_buffer, m_current_pointer, buffer_size);\n\t\tm_current_pointer += buffer_size;\n\t\treturn;\n\t}\n\n\tu8* buffer = (u8*)_buffer;\n\tu32 elapsed_in_window = m_current_window_size - u32(offset_inside_window);\n\n\tdo\n\t{\n\t\tMemory.mem_copy(buffer, m_current_pointer, elapsed_in_window);\n\t\tbuffer += elapsed_in_window;\n\t\tbuffer_size -= elapsed_in_window;\n\t\tadvance(elapsed_in_window);\n\n\t\telapsed_in_window = m_current_window_size;\n\t} while (m_current_window_size < buffer_size);\n\n\tMemory.mem_copy(buffer, m_current_pointer, buffer_size);\n\tadvance(buffer_size);\n}'''


def native_newlines(data: bytes, replacement: bytes) -> bytes:
    if b"\r\n" in data[:2048]:
        return replacement.replace(b"\n", b"\r\n")
    return replacement


def replace_exact(path: Path, old: bytes, new: bytes, label: str) -> None:
    data = path.read_bytes()
    old_native = native_newlines(data, old)
    new_native = native_newlines(data, new)
    count = data.count(old_native)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one legacy pattern, found {count}")
    updated = data.replace(old_native, new_native, 1)
    if old_native in updated:
        raise RuntimeError(f"{label}: legacy pattern remains after migration")
    path.write_bytes(updated)


def disable_unavailable_x64_lua_jit(root: Path) -> None:
    targets = [root / "xr_3da" / "xrGame" / "script_storage.cpp", root / "xrSE_Factory" / "script_storage.cpp"]
    for path in targets:
        if not path.is_file(): raise FileNotFoundError(path)
        replace_exact(path, JIT_GUARD_OLD, JIT_GUARD_NEW, f"{path.relative_to(root)} Win64 JIT guard")
    for path in targets:
        data = path.read_bytes(); expected = native_newlines(data, JIT_GUARD_NEW)
        if data.count(expected) != 1: raise RuntimeError(f"{path.relative_to(root)}: Win64 JIT guard validation failed")
    print("[x64-lua] Lua JIT initialization disabled on Win64 in xrGame and xrSE_Factory; Win32 JIT behavior preserved")


def fix_ispatial_pointer_truncation(root: Path) -> None:
    path = root / "xr_3da" / "ISpatial.h"
    if not path.is_file(): raise FileNotFoundError(path)
    replace_exact(path, ISPATIAL_EMPTY_OLD, ISPATIAL_EMPTY_NEW, "xr_3da/ISpatial.h _empty pointer truncation")
    data = path.read_bytes(); expected = native_newlines(data, ISPATIAL_EMPTY_NEW)
    if data.count(expected) != 1: raise RuntimeError("xr_3da/ISpatial.h: pointer-safe _empty validation failed")
    print("[x64-spatial] ISpatial_NODE::_empty no longer truncates 64-bit child pointers through legacy ptrt casts")


def fix_stream_reader_pointer_width(root: Path) -> None:
    inline_path = root / "xrCore" / "stream_reader_inline.h"; source_path = root / "xrCore" / "stream_reader.cpp"
    for path in (inline_path, source_path):
        if not path.is_file(): raise FileNotFoundError(path)
    replace_exact(inline_path, STREAM_TELL_OLD, STREAM_TELL_NEW, "xrCore/stream_reader_inline.h tell pointer width")
    replace_exact(source_path, STREAM_ADVANCE_OLD, STREAM_ADVANCE_NEW, "xrCore/stream_reader.cpp advance pointer width")
    replace_exact(source_path, STREAM_READ_OLD, STREAM_READ_NEW, "xrCore/stream_reader.cpp read pointer width")
    inline_data = inline_path.read_bytes()
    if inline_data.count(native_newlines(inline_data, STREAM_TELL_NEW)) != 1: raise RuntimeError("xrCore/stream_reader_inline.h: pointer-width-safe tell validation failed")
    source_data = source_path.read_bytes()
    if source_data.count(native_newlines(source_data, STREAM_ADVANCE_NEW)) != 1: raise RuntimeError("xrCore/stream_reader.cpp: pointer-width-safe advance validation failed")
    if source_data.count(native_newlines(source_data, STREAM_READ_NEW)) != 1: raise RuntimeError("xrCore/stream_reader.cpp: pointer-width-safe read validation failed")
    print("[x64-stream] CStreamReader tell/advance/read preserve native pointer width before checked u32 narrowing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply incremental runtime compatibility fixes for the RC6 Win64 port.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    disable_unavailable_x64_lua_jit(root)
    fix_ispatial_pointer_truncation(root)
    fix_stream_reader_pointer_width(root)
    enable_vulkan_bootstrap(root)
    enable_vulkan_capability_probe(root)
    harden_vulkan_capability_probe(root)
    harden_vulkan_shader_pipeline_cache(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
