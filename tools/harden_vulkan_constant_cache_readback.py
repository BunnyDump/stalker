from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    header = root.resolve() / "xr_3da" / "r_constants_cache.h"
    if not header.is_file():
        raise FileNotFoundError(header)

    text = header.read_text(encoding="utf-8")

    access = "\tICF T* access(u32 id)\n\t{\n\t\treturn &array[id];\n\t}\n"
    access_const = access + "\tICF const T* access(u32 id) const\n\t{\n\t\treturn &array[id];\n\t}\n"
    if "ICF const T* access(u32 id) const" not in text:
        if access not in text:
            raise RuntimeError("constant-cache access marker missing")
        text = text.replace(access, access_const, 1)

    r_lo = "\tICF u32 r_lo()\n\t{\n\t\treturn lo;\n\t}\n"
    r_lo_const = r_lo + "\tICF u32 r_lo() const\n\t{\n\t\treturn lo;\n\t}\n"
    if "ICF u32 r_lo() const" not in text:
        if r_lo not in text:
            raise RuntimeError("constant-cache r_lo marker missing")
        text = text.replace(r_lo, r_lo_const, 1)

    r_hi = "\tICF u32 r_hi()\n\t{\n\t\treturn hi;\n\t}\n"
    r_hi_const = r_hi + "\tICF u32 r_hi() const\n\t{\n\t\treturn hi;\n\t}\n"
    if "ICF u32 r_hi() const" not in text:
        if r_hi not in text:
            raise RuntimeError("constant-cache r_hi marker missing")
        text = text.replace(r_hi, r_hi_const, 1)

    array_f = "\tt_f& get_array_f()\n\t{\n\t\treturn c_f;\n\t}\n"
    array_f_const = array_f + "\tconst t_f& get_array_f() const\n\t{\n\t\treturn c_f;\n\t}\n"
    if "const t_f& get_array_f() const" not in text:
        if array_f not in text:
            raise RuntimeError("constant-array float-cache marker missing")
        text = text.replace(array_f, array_f_const, 1)

    header.write_text(text, encoding="utf-8")
    final = header.read_text(encoding="utf-8")
    for token in (
        "ICF const T* access(u32 id) const",
        "ICF u32 r_lo() const",
        "ICF u32 r_hi() const",
        "const t_f& get_array_f() const",
    ):
        if token not in final:
            raise RuntimeError(f"constant-cache readback hardening missing {token}")

    print("[vulkan-constant-cache] const-safe float-register cache readback exposed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Expose const-safe SHOC constant-cache readback for Vulkan UBO snapshots.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
