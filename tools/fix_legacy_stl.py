from __future__ import annotations

import argparse
from pathlib import Path

SOURCE_SUFFIXES = {".h", ".hpp", ".hh", ".cpp", ".cxx", ".cc", ".inl"}
OLD = b"std::binary_function"
NEW = b"xr_binary_function"
HELPER = b'''template <class Arg1, class Arg2, class Result> struct xr_binary_function\n{\n\ttypedef Arg1 first_argument_type;\n\ttypedef Arg2 second_argument_type;\n\ttypedef Result result_type;\n};\n'''


def inject_helper(header: Path) -> bool:
    data = header.read_bytes()
    if b"struct xr_binary_function" in data:
        return False

    marker = b"using std::swap;\n"
    pos = data.find(marker)
    if pos < 0:
        raise RuntimeError(f"Unable to find STL compatibility insertion point in {header}")

    pos += len(marker)
    data = data[:pos] + b"\n" + HELPER + data[pos:]
    header.write_bytes(data)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace removed std::binary_function with an X-Ray local compatibility base."
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

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        data = path.read_bytes()
        count = data.count(OLD)
        if not count:
            continue
        path.write_bytes(data.replace(OLD, NEW))
        replacements += count
        changed_files.append((path, count))
        print(f"[legacy-stl] {path.relative_to(root)}: replaced {count}")

    remaining = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if OLD in path.read_bytes():
            remaining.append(path.relative_to(root))

    if remaining:
        print("[legacy-stl] ERROR: unresolved std::binary_function occurrences:")
        for path in remaining:
            print(f"  {path}")
        return 2

    if replacements == 0:
        print("[legacy-stl] ERROR: no std::binary_function occurrences were found at the pinned RC6 source revision")
        return 3

    print(
        f"[legacy-stl] helper_added={helper_added} files={len(changed_files)} "
        f"replacements={replacements} remaining=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
