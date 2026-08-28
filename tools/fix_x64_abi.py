from __future__ import annotations

import argparse
from pathlib import Path

RAISE_OLD = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(DWORD), (DWORD*)&tn);"
RAISE_NEW = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(ULONG_PTR), reinterpret_cast<const ULONG_PTR*>(&tn));"
APP_PATH_OLD = b"extern char g_application_path[256];"
APP_PATH_NEW = b"#ifdef _WIN64\nchar g_application_path[256] = {};\n#else\nextern char g_application_path[256];\n#endif"


def replace_exact(path: Path, old: bytes, new: bytes, label: str, require_old_absent: bool = True) -> None:
    data = path.read_bytes()
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one legacy pattern, found {count}")

    # Preserve native source line endings when inserting multiline code.
    if b"\r\n" in data[:1024]:
        new = new.replace(b"\n", b"\r\n")

    updated = data.replace(old, new, 1)
    if require_old_absent and old in updated:
        raise RuntimeError(f"{label}: legacy pattern remains after migration")
    path.write_bytes(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted Win64 ABI/linkage fixes to X-Ray runtime sources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    math_path = root / "xrCore" / "_math.cpp"
    core_path = root / "xrCore" / "xrCore.cpp"
    for path in (math_path, core_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    replace_exact(math_path, RAISE_OLD, RAISE_NEW, "xrCore/_math.cpp RaiseException")
    print("[x64-abi] xrCore/_math.cpp: thread-name RaiseException payload migrated DWORD -> ULONG_PTR")

    # CrashHandler.cpp owns this symbol in the legacy Win32 build, but the RC6
    # x64 project intentionally excludes BlackBox/CrashHandler. Supply storage
    # only for Win64 so the original Win32 ownership and ABI remain untouched.
    replace_exact(
        core_path,
        APP_PATH_OLD,
        APP_PATH_NEW,
        "xrCore/xrCore.cpp g_application_path",
        require_old_absent=False,
    )
    migrated = core_path.read_bytes()
    if b"#ifdef _WIN64" not in migrated or b"char g_application_path[256] = {};" not in migrated:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win64 storage definition was not installed")
    if migrated.count(APP_PATH_OLD) != 1:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win32 extern ownership was not preserved exactly once")
    print("[x64-abi] xrCore/xrCore.cpp: supplied Win64 g_application_path storage; Win32 keeps CrashHandler ownership")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
