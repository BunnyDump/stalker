from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", MSBUILD_NS)
Q = lambda name: f"{{{MSBUILD_NS}}}{name}"
MACHINE_I386_RE = re.compile(r"(?i)(?:^|\s)/MACHINE:I386(?=\s|$)")

RAISE_OLD = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(DWORD), (DWORD*)&tn);"
RAISE_NEW = b"RaiseException(0x406D1388, 0, sizeof(tn) / sizeof(ULONG_PTR), reinterpret_cast<const ULONG_PTR*>(&tn));"
APP_PATH_OLD = b"extern char g_application_path[256];"
APP_PATH_NEW = b"#ifdef _WIN64\nchar g_application_path[256] = {};\n#else\nextern char g_application_path[256];\n#endif"
LUA_STUB_OLD = b'#include "lua.h"'
LUA_STUB_NEW = b'#define LUA_CORE\n#include "lua.h"'
CAST_INT_OLD = b"cast_int(pc - p->code)"
CAST_INT_NEW = b"cast(int, pc - p->code)"


def native_newlines(data: bytes, replacement: bytes) -> bytes:
    if b"\r\n" in data[:2048]:
        return replacement.replace(b"\n", b"\r\n")
    return replacement


def replace_exact(path: Path, old: bytes, new: bytes, label: str, require_old_absent: bool = True) -> None:
    data = path.read_bytes()
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one legacy pattern, found {count}")
    new = native_newlines(data, new)
    updated = data.replace(old, new, 1)
    if require_old_absent and old in updated:
        raise RuntimeError(f"{label}: legacy pattern remains after migration")
    path.write_bytes(updated)


def is_x64_condition(condition: str | None) -> bool:
    if not condition:
        return False
    return "|x64" in condition.replace(" ", "").lower()


def clean_machine_option(text: str) -> tuple[str, int]:
    count = len(MACHINE_I386_RE.findall(text))
    if not count:
        return text, 0
    updated = MACHINE_I386_RE.sub(" ", text)
    updated = re.sub(r"[ \t]{2,}", " ", updated)
    updated = "\n".join(line.strip() for line in updated.splitlines()).strip()
    return updated or "%(AdditionalOptions)", count


def fix_project_machine(path: Path) -> tuple[int, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    removed_i386 = 0
    changed_target = 0

    for group in root.iter():
        if not is_x64_condition(group.get("Condition")):
            continue
        for tool_name in ("Link", "Lib", "Librarian"):
            tool = group.find(Q(tool_name))
            if tool is None:
                continue
            options = tool.find(Q("AdditionalOptions"))
            if options is not None and options.text:
                updated, count = clean_machine_option(options.text)
                if count:
                    options.text = updated
                    removed_i386 += count
            target = tool.find(Q("TargetMachine"))
            if target is not None and (target.text or "").strip().lower() == "machinex86":
                target.text = "MachineX64"
                changed_target += 1

    if removed_i386 or changed_target:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return removed_i386, changed_target


def validate_project_machines(root: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(root.rglob("*.vcxproj")):
        try:
            project = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for group in project.iter():
            if not is_x64_condition(group.get("Condition")):
                continue
            for tool_name in ("Link", "Lib", "Librarian"):
                tool = group.find(Q(tool_name))
                if tool is None:
                    continue
                options = tool.find(Q("AdditionalOptions"))
                target = tool.find(Q("TargetMachine"))
                if options is not None and options.text and re.search(r"(?i)/MACHINE:I386", options.text):
                    bad.append(f"{path.relative_to(root)}: {group.get('Condition')} {tool_name}/AdditionalOptions")
                if target is not None and (target.text or "").strip().lower() == "machinex86":
                    bad.append(f"{path.relative_to(root)}: {group.get('Condition')} {tool_name}/TargetMachine")
    return bad


def fix_x64_linker_machine(root: Path) -> None:
    projects = changed = removed = targets = 0
    for path in sorted(root.rglob("*.vcxproj")):
        projects += 1
        try:
            count, target_count = fix_project_machine(path)
        except ET.ParseError:
            continue
        if count or target_count:
            changed += 1
            removed += count
            targets += target_count
            print(
                f"[x64-link] {path.relative_to(root)}: "
                f"removed_i386={count} target_machine_x64={target_count}"
            )

    bad = validate_project_machines(root)
    if bad:
        details = "\n".join(f"  {item}" for item in bad)
        raise RuntimeError(f"forced x86 linker settings remain in x64 configs:\n{details}")
    print(
        f"[x64-link] projects={projects} changed={changed} "
        f"removed_i386={removed} target_machine_x64={targets} remaining=0"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted Win64 ABI/linkage fixes to X-Ray runtime sources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    math_path = root / "xrCore" / "_math.cpp"
    core_path = root / "xrCore" / "xrCore.cpp"
    lua_stub = root / "xrLua" / "src" / "ljit_x64_stub.c"
    lua_debug = root / "xrLua" / "src" / "ldebug.c"
    for path in (math_path, core_path, lua_stub, lua_debug):
        if not path.is_file():
            raise FileNotFoundError(path)

    # Project-level linker options copied from the original VS projects still
    # contain /MACHINE:I386 in several x64 configurations. Remove only the x64
    # forcing while leaving every Win32 configuration untouched.
    fix_x64_linker_machine(root)

    replace_exact(math_path, RAISE_OLD, RAISE_NEW, "xrCore/_math.cpp RaiseException")
    print("[x64-abi] xrCore/_math.cpp: thread-name RaiseException payload migrated DWORD -> ULONG_PTR")

    # CrashHandler.cpp owns this symbol in the legacy Win32 build, but the RC6
    # x64 project intentionally excludes BlackBox/CrashHandler. Supply storage
    # only for Win64 so the original Win32 ownership and ABI remain untouched.
    replace_exact(core_path, APP_PATH_OLD, APP_PATH_NEW, "xrCore/xrCore.cpp g_application_path", require_old_absent=False)
    migrated = core_path.read_bytes()
    if b"#ifdef _WIN64" not in migrated or b"char g_application_path[256] = {};" not in migrated:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win64 storage definition was not installed")
    if migrated.count(APP_PATH_OLD) != 1:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win32 extern ownership was not preserved exactly once")
    print("[x64-abi] xrCore/xrCore.cpp: supplied Win64 g_application_path storage; Win32 keeps CrashHandler ownership")

    # The x64 interpreter stub is part of xrLua itself. LUA_BUILD_AS_DLL makes
    # LUA_API dllimport unless LUA_CORE is defined before lua.h, which makes
    # MSVC reject these definitions with C2491. Match only the include line so
    # the migration is independent of CRLF/LF source line endings.
    replace_exact(lua_stub, LUA_STUB_OLD, LUA_STUB_NEW, "xrLua/ljit_x64_stub.c LUA_CORE", require_old_absent=False)
    if lua_stub.read_bytes().count(b"#define LUA_CORE") != 1:
        raise RuntimeError("xrLua/ljit_x64_stub.c: LUA_CORE was not installed exactly once")
    print("[x64-abi] xrLua/src/ljit_x64_stub.c: x64 JIT stubs now export from xrLua instead of dllimport")

    # Lua 5.1/LuaJIT-era cast_int is absent from this tree. The x64 fallback in
    # ldebug.c only needs an explicit narrowing through Lua's existing cast macro.
    replace_exact(lua_debug, CAST_INT_OLD, CAST_INT_NEW, "xrLua/ldebug.c currentpc cast")
    print("[x64-abi] xrLua/src/ldebug.c: removed undefined cast_int from Win64 currentpc fallback")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
