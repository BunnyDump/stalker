from __future__ import annotations

import argparse
from pathlib import Path

SOURCE_SUFFIXES = {".h", ".hpp", ".hh", ".cpp", ".cxx", ".cc", ".inl"}
SCAN_DIRS = ("xrCore", "xr_3da")
OLD = b"std::binary_function"
NEW = b"xr_binary_function"
HELPER = b'''template <class Arg1, class Arg2, class Result> struct xr_binary_function\n{\n\ttypedef Arg1 first_argument_type;\n\ttypedef Arg2 second_argument_type;\n\ttypedef Result result_type;\n};\n'''


def inject_helper(header: Path) -> bool:
    data = header.read_bytes()
    if b"struct xr_binary_function" in data:
        return False

    # Preserve the source file's native line endings. Insert immediately after
    # the include guard so the helper is available to _stl_extensions itself and
    # all runtime headers included later through xrCore.h.
    nl = b"\r\n" if b"\r\n" in data[:512] else b"\n"
    lines = data.splitlines(keepends=True)
    if (
        len(lines) < 2
        or b"#ifndef _STL_EXT_internal" not in lines[0]
        or b"#define _STL_EXT_internal" not in lines[1]
    ):
        raise RuntimeError(f"Unexpected _stl_extensions.h include guard in {header}")

    helper = HELPER.replace(b"\n", nl)
    data = b"".join(lines[:2]) + nl + helper + nl + b"".join(lines[2:])
    header.write_bytes(data)
    return True


def source_files(root: Path):
    for dirname in SCAN_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace removed std::binary_function in X-Ray runtime sources."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    header = root / "xrCore" / "_stl_extensions.h"
    if not header.is_file():
        raise FileNotFoundError(header)

    helper_added = inject_helper(header)
    replacements = 0
    changed_files = []
    files = list(source_files(root))

    for path in files:
        data = path.read_bytes()
        count = data.count(OLD)
        if not count:
            continue
        path.write_bytes(data.replace(OLD, NEW))
        replacements += count
        changed_files.append((path, count))
        print(f"[legacy-stl] {path.relative_to(root)}: replaced {count}")

    remaining = []
    for path in files:
        if OLD in path.read_bytes():
            remaining.append(path.relative_to(root))

    if remaining:
        print("[legacy-stl] ERROR: unresolved runtime std::binary_function occurrences:")
        for path in remaining:
            print(f"  {path}")
        return 2

    if replacements == 0:
        print("[legacy-stl] ERROR: no runtime std::binary_function occurrences were found")
        return 3

    print(
        f"[legacy-stl] helper_added={helper_added} files={len(changed_files)} "
        f"replacements={replacements} remaining=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
