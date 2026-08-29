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
WINNT_OLD = b"#define _WIN32_WINNT 0x0500"
WINNT_NEW = b"#define _WIN32_WINNT 0x0601"
SYSMETRICS_OLD = b"#define NOSYSMETRICS"
SYSMETRICS_NEW = b"// NOSYSMETRICS disabled for x64: engine requires GetSystemMetrics declarations"
DLGPROC_OLD = b"static BOOL CALLBACK logDlgProc(HWND hw, UINT msg, WPARAM wp, LPARAM lp)"
DLGPROC_NEW = b"static INT_PTR CALLBACK logDlgProc(HWND hw, UINT msg, WPARAM wp, LPARAM lp)"


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


def fix_xrsound_x64_project(root: Path) -> None:
    path = root / "xrSound" / "xrSound.vcxproj"
    tree = ET.parse(path)
    project = tree.getroot()

    # DirectSound backend is intentionally disabled on Win64 by sound.cpp and
    # SoundRender_CoreD.cpp is already excluded. Exclude its target peer too,
    # otherwise it links against the absent SoundRenderD global.
    target_found = False
    target_excluded = False
    for item in project.findall(f".//{Q('ClCompile')}"):
        include = (item.get("Include") or "").replace("/", "\\").lower()
        if include.endswith("soundrender_targetd.cpp"):
            target_found = True
            for node in item.findall(Q("ExcludedFromBuild")):
                cond = (node.get("Condition") or "").replace(" ", "").lower()
                if "$(platform)" in cond and "x64" in cond and (node.text or "").strip().lower() == "true":
                    target_excluded = True
                    break
            if not target_excluded:
                node = ET.SubElement(item, Q("ExcludedFromBuild"))
                node.set("Condition", "'$(Platform)'=='x64'")
                node.text = "true"
                target_excluded = True
            break
    if not target_found or not target_excluded:
        raise RuntimeError("xrSound: unable to exclude SoundRender_TargetD.cpp for x64")

    # vorbisfile_static.lib contains the file/stream wrapper but depends on the
    # core Vorbis decoder library. The historical xrSound project omitted it.
    dependency_changes = 0
    for group in project.findall(Q("ItemDefinitionGroup")):
        if not is_x64_condition(group.get("Condition")):
            continue
        link = group.find(Q("Link"))
        if link is None:
            continue
        deps = link.find(Q("AdditionalDependencies"))
        if deps is None or not deps.text:
            continue
        items = [part.strip() for part in deps.text.split(";") if part.strip()]
        lower = [part.lower() for part in items]
        if "vorbisfile_static_d.lib" in lower and "vorbis_static_d.lib" not in lower:
            idx = lower.index("vorbisfile_static_d.lib")
            items.insert(idx, "vorbis_static_d.lib")
            dependency_changes += 1
        elif "vorbisfile_static.lib" in lower and "vorbis_static.lib" not in lower:
            idx = lower.index("vorbisfile_static.lib")
            items.insert(idx, "vorbis_static.lib")
            dependency_changes += 1
        deps.text = ";".join(items)

    if dependency_changes == 0:
        raise RuntimeError("xrSound: no x64 Vorbis dependency lists were repaired")

    tree.write(path, encoding="utf-8", xml_declaration=True)

    # Re-read and validate the exact x64 invariants after serialization.
    check = ET.parse(path).getroot()
    bad_deps: list[str] = []
    for group in check.findall(Q("ItemDefinitionGroup")):
        if not is_x64_condition(group.get("Condition")):
            continue
        link = group.find(Q("Link"))
        if link is None:
            continue
        deps = link.find(Q("AdditionalDependencies"))
        text = (deps.text if deps is not None and deps.text else "").lower()
        if "vorbisfile_static_d.lib" in text and "vorbis_static_d.lib" not in text:
            bad_deps.append(group.get("Condition") or "<unknown>")
        if "vorbisfile_static.lib" in text and "vorbis_static.lib" not in text:
            bad_deps.append(group.get("Condition") or "<unknown>")
    if bad_deps:
        raise RuntimeError(f"xrSound: unresolved Vorbis x64 dependency lists: {bad_deps}")

    print(
        f"[x64-sound] SoundRender_TargetD.cpp excluded for x64; "
        f"Vorbis dependency lists repaired={dependency_changes}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted Win64 ABI/linkage fixes to X-Ray runtime sources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    math_path = root / "xrCore" / "_math.cpp"
    core_path = root / "xrCore" / "xrCore.cpp"
    platform_path = root / "xrCore" / "xrCore_platform.h"
    xray_path = root / "xr_3da" / "x_ray.cpp"
    lua_stub = root / "xrLua" / "src" / "ljit_x64_stub.c"
    lua_debug = root / "xrLua" / "src" / "ldebug.c"
    for path in (math_path, core_path, platform_path, xray_path, lua_stub, lua_debug):
        if not path.is_file():
            raise FileNotFoundError(path)

    # Project-level linker options copied from the original VS projects still
    # contain /MACHINE:I386 in several x64 configurations. Remove only the x64
    # forcing while leaving every Win32 configuration untouched.
    fix_x64_linker_machine(root)
    fix_xrsound_x64_project(root)

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

    # The historical platform header defines NOSYSMETRICS before windows.h.
    # Modern Windows SDKs then intentionally hide GetSystemMetrics and SM_CX/CYSCREEN.
    # RC6 uses these APIs in the x64 engine, so retain the declarations and target
    # Windows 7 API level, which also exposes SetProcessDPIAware used by RC6.
    replace_exact(platform_path, WINNT_OLD, WINNT_NEW, "xrCore/xrCore_platform.h _WIN32_WINNT")
    replace_exact(platform_path, SYSMETRICS_OLD, SYSMETRICS_NEW, "xrCore/xrCore_platform.h NOSYSMETRICS")
    print("[x64-winapi] xrCore/xrCore_platform.h: Windows 7 API level and system metrics declarations enabled")

    # DLGPROC returns INT_PTR. BOOL happened to be ABI-compatible on 32-bit,
    # but it is a 32-bit return value and no longer matches DLGPROC on Win64.
    replace_exact(xray_path, DLGPROC_OLD, DLGPROC_NEW, "xr_3da/x_ray.cpp logDlgProc Win64 ABI")
    print("[x64-winapi] xr_3da/x_ray.cpp: logDlgProc return type migrated BOOL -> INT_PTR")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
