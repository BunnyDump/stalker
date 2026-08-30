from __future__ import annotations

import argparse
from pathlib import Path

JIT_GUARD_OLD = b"#ifdef USE_JIT"
JIT_GUARD_NEW = b"#if defined(USE_JIT) && !defined(_WIN64)"

ISPATIAL_EMPTY_OLD = b'''\tBOOL _empty()\n\t{\n\t\treturn items.empty() && (0 == (ptrt(children[0]) | ptrt(children[1]) | ptrt(children[2]) | ptrt(children[3]) |\n\t\t\t\t\t\t\t\t\t   ptrt(children[4]) | ptrt(children[5]) | ptrt(children[6]) | ptrt(children[7])));\n\t}'''
ISPATIAL_EMPTY_NEW = b'''\tBOOL _empty()\n\t{\n\t\treturn items.empty() && children[0] == 0 && children[1] == 0 && children[2] == 0 && children[3] == 0 &&\n\t\t\tchildren[4] == 0 && children[5] == 0 && children[6] == 0 && children[7] == 0;\n\t}'''


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
    targets = [
        root / "xr_3da" / "xrGame" / "script_storage.cpp",
        root / "xrSE_Factory" / "script_storage.cpp",
    ]

    for path in targets:
        if not path.is_file():
            raise FileNotFoundError(path)
        replace_exact(path, JIT_GUARD_OLD, JIT_GUARD_NEW, f"{path.relative_to(root)} Win64 JIT guard")

    for path in targets:
        data = path.read_bytes()
        expected = native_newlines(data, JIT_GUARD_NEW)
        if data.count(expected) != 1:
            raise RuntimeError(f"{path.relative_to(root)}: Win64 JIT guard validation failed")

    print("[x64-lua] Lua JIT initialization disabled on Win64 in xrGame and xrSE_Factory; Win32 JIT behavior preserved")


def fix_ispatial_pointer_truncation(root: Path) -> None:
    path = root / "xr_3da" / "ISpatial.h"
    if not path.is_file():
        raise FileNotFoundError(path)

    replace_exact(path, ISPATIAL_EMPTY_OLD, ISPATIAL_EMPTY_NEW, "xr_3da/ISpatial.h _empty pointer truncation")

    data = path.read_bytes()
    expected = native_newlines(data, ISPATIAL_EMPTY_NEW)
    if data.count(expected) != 1:
        raise RuntimeError("xr_3da/ISpatial.h: pointer-safe _empty validation failed")

    print("[x64-spatial] ISpatial_NODE::_empty no longer truncates 64-bit child pointers through legacy ptrt casts")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply incremental runtime compatibility fixes for the RC6 Win64 port.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    disable_unavailable_x64_lua_jit(root)
    fix_ispatial_pointer_truncation(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
