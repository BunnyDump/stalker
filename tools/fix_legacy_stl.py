from __future__ import annotations

import argparse
from pathlib import Path

SOURCE_SUFFIXES = {".h", ".hpp", ".hh", ".cpp", ".cxx", ".cc", ".inl"}
SCAN_DIRS = ("xrCore", "xr_3da")
REPLACEMENTS = (
    (b"std::binary_function", b"xr_binary_function"),
    (b"std::unary_function", b"xr_unary_function"),
    (b"std::bind2nd", b"xr_bind2nd"),
)
HELPER = b'''template <class Arg1, class Arg2, class Result> struct xr_binary_function\n{\n\ttypedef Arg1 first_argument_type;\n\ttypedef Arg2 second_argument_type;\n\ttypedef Result result_type;\n};\n\ntemplate <class Arg, class Result> struct xr_unary_function\n{\n\ttypedef Arg argument_type;\n\ttypedef Result result_type;\n};\n\ntemplate <class Operation, class Value> class xr_binder2nd\n{\n\tOperation op;\n\tValue value;\n\n  public:\n\txr_binder2nd(const Operation& operation, const Value& bound_value) : op(operation), value(bound_value) {}\n\n\ttemplate <class Arg> auto operator()(const Arg& arg) const -> decltype(op(arg, value))\n\t{\n\t\treturn op(arg, value);\n\t}\n};\n\ntemplate <class Operation, class Value>\nxr_binder2nd<Operation, Value> xr_bind2nd(const Operation& op, const Value& value)\n{\n\treturn xr_binder2nd<Operation, Value>(op, value);\n}\n'''


def inject_helper(header: Path) -> bool:
    data = header.read_bytes()
    if b"struct xr_binary_function" in data and b"struct xr_unary_function" in data and b"xr_bind2nd" in data:
        return False

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
        description="Replace removed legacy STL functor adapters in X-Ray runtime sources."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    header = root / "xrCore" / "_stl_extensions.h"
    if not header.is_file():
        raise FileNotFoundError(header)

    helper_added = inject_helper(header)
    totals = {old.decode(): 0 for old, _ in REPLACEMENTS}
    changed_files = set()
    files = list(source_files(root))

    for path in files:
        data = path.read_bytes()
        updated = data
        file_count = 0
        for old, new in REPLACEMENTS:
            count = updated.count(old)
            if count:
                updated = updated.replace(old, new)
                totals[old.decode()] += count
                file_count += count
        if updated != data:
            path.write_bytes(updated)
            changed_files.add(path)
            print(f"[legacy-stl] {path.relative_to(root)}: replaced {file_count}")

    remaining = []
    for path in files:
        data = path.read_bytes()
        for old, _ in REPLACEMENTS:
            if old in data:
                remaining.append((path.relative_to(root), old.decode()))

    if remaining:
        print("[legacy-stl] ERROR: unresolved runtime legacy STL adapters:")
        for path, token in remaining:
            print(f"  {path}: {token}")
        return 2

    if totals["std::binary_function"] == 0:
        print("[legacy-stl] ERROR: no std::binary_function occurrences were found")
        return 3

    print(
        "[legacy-stl] helper_added={} files={} binary={} unary={} bind2nd={} remaining=0".format(
            helper_added,
            len(changed_files),
            totals["std::binary_function"],
            totals["std::unary_function"],
            totals["std::bind2nd"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
