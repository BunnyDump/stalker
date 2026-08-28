from __future__ import annotations

import argparse
from pathlib import Path

OLD = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(DWORD), (DWORD*)&tn);"
NEW = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(ULONG_PTR), reinterpret_cast<const ULONG_PTR*>(&tn));"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted Win64 ABI fixes to X-Ray runtime sources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    path = root / "xrCore" / "_math.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    data = path.read_bytes()
    count = data.count(OLD)
    if count != 1:
        print(f"[x64-abi] ERROR: expected exactly one legacy RaiseException call, found {count}")
        return 2

    updated = data.replace(OLD, NEW, 1)
    if OLD in updated:
        print("[x64-abi] ERROR: legacy RaiseException ABI pattern remains")
        return 3

    path.write_bytes(updated)
    print("[x64-abi] xrCore/_math.cpp: thread-name RaiseException payload migrated DWORD -> ULONG_PTR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
