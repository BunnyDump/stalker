#!/usr/bin/env python3
"""Validate that private PE imports of a Windows distribution are present beside the binaries."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# DLLs supplied by supported Windows itself. VC runtime DLLs are intentionally
# excluded: a portable RC6 package must carry the exact redistributable runtime
# it was built against instead of assuming it is installed globally.
WINDOWS_SYSTEM_DLLS = {
    "advapi32.dll", "avifil32.dll", "avrt.dll", "bcrypt.dll", "bcryptprimitives.dll",
    "cabinet.dll", "cfgmgr32.dll", "combase.dll", "comctl32.dll", "comdlg32.dll",
    "crypt32.dll", "d3d9.dll", "dbghelp.dll", "dinput8.dll", "dnsapi.dll",
    "dsound.dll", "dwmapi.dll", "gdi32.dll", "gdi32full.dll", "imm32.dll",
    "iphlpapi.dll", "kernel32.dll", "kernelbase.dll", "ksuser.dll", "mf.dll",
    "mfplat.dll", "mpr.dll", "msacm32.dll", "msimg32.dll", "msvcrt.dll",
    "msvfw32.dll", "ncrypt.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll",
    "powrprof.dll", "propsys.dll", "psapi.dll", "rpcrt4.dll", "sechost.dll",
    "setupapi.dll", "shell32.dll", "shlwapi.dll", "ucrtbase.dll", "user32.dll",
    "userenv.dll", "version.dll", "winhttp.dll", "wininet.dll", "winmm.dll",
    "wldap32.dll", "ws2_32.dll", "wsock32.dll", "wtsapi32.dll",
}
SYSTEM_PREFIXES = ("api-ms-win-", "ext-ms-win-")


class PEFormatError(ValueError):
    pass


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise PEFormatError("truncated 16-bit field")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise PEFormatError("truncated 32-bit field")
    return struct.unpack_from("<I", data, offset)[0]


def pe_imports(path: Path) -> list[str]:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise PEFormatError("missing MZ header")
    pe_offset = _u32(data, 0x3C)
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise PEFormatError("missing PE signature")

    coff = pe_offset + 4
    section_count = _u16(data, coff + 2)
    optional_size = _u16(data, coff + 16)
    optional = coff + 20
    magic = _u16(data, optional)
    if magic == 0x20B:  # PE32+
        data_directory = optional + 112
    elif magic == 0x10B:  # PE32
        data_directory = optional + 96
    else:
        raise PEFormatError(f"unsupported optional header 0x{magic:04X}")

    # IMAGE_DIRECTORY_ENTRY_IMPORT = 1.
    import_rva = _u32(data, data_directory + 8)
    if import_rva == 0:
        return []

    sections_offset = optional + optional_size
    sections: list[tuple[int, int, int]] = []
    for index in range(section_count):
        entry = sections_offset + index * 40
        if entry + 40 > len(data):
            raise PEFormatError("truncated section table")
        virtual_size = _u32(data, entry + 8)
        virtual_address = _u32(data, entry + 12)
        raw_size = _u32(data, entry + 16)
        raw_pointer = _u32(data, entry + 20)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def rva_to_offset(rva: int) -> int:
        for virtual_address, span, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + span:
                offset = raw_pointer + (rva - virtual_address)
                if offset < len(data):
                    return offset
        # Header RVAs are legal too.
        if rva < sections_offset and rva < len(data):
            return rva
        raise PEFormatError(f"RVA 0x{rva:X} is not mapped")

    descriptor = rva_to_offset(import_rva)
    imports: list[str] = []
    for _ in range(4096):
        if descriptor + 20 > len(data):
            raise PEFormatError("truncated import descriptor table")
        fields = struct.unpack_from("<IIIII", data, descriptor)
        if fields == (0, 0, 0, 0, 0):
            break
        name_rva = fields[3]
        name_offset = rva_to_offset(name_rva)
        terminator = data.find(b"\0", name_offset, min(len(data), name_offset + 512))
        if terminator < 0:
            raise PEFormatError("unterminated import DLL name")
        try:
            imports.append(data[name_offset:terminator].decode("ascii"))
        except UnicodeDecodeError as exc:
            raise PEFormatError("non-ASCII import DLL name") from exc
        descriptor += 20
    else:
        raise PEFormatError("unreasonably large import descriptor table")

    return imports


def is_windows_system_dll(name: str) -> bool:
    lowered = name.lower()
    return lowered in WINDOWS_SYSTEM_DLLS or lowered.startswith(SYSTEM_PREFIXES)


def validate_bin(bin_dir: Path) -> list[str]:
    if not bin_dir.is_dir():
        return [f"missing bin directory: {bin_dir}"]

    files = {path.name.lower(): path for path in bin_dir.iterdir() if path.is_file()}
    pe_files = [path for path in files.values() if path.suffix.lower() in {".exe", ".dll"}]
    errors: list[str] = []
    private_edges = 0

    for path in sorted(pe_files, key=lambda item: item.name.lower()):
        try:
            imports = pe_imports(path)
        except (OSError, PEFormatError) as exc:
            errors.append(f"cannot parse PE imports for {path.name}: {exc}")
            continue

        for dependency in imports:
            lowered = dependency.lower()
            if is_windows_system_dll(lowered):
                continue
            private_edges += 1
            if lowered not in files:
                errors.append(f"{path.name} imports missing private runtime DLL: {dependency}")

    if not errors:
        print(f"OK: recursive PE runtime closure passed ({len(pe_files)} PE files, {private_edges} private import edges)")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate recursive Windows PE runtime dependency closure.")
    parser.add_argument("bin", type=Path, help="Distribution bin directory")
    args = parser.parse_args()
    errors = validate_bin(args.bin.resolve())
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
