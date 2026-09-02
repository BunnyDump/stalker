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
GPU_VENDOR_HEADERS_OLD = b'''#ifndef _EDITOR
#include "NVAPI/nvapi.h"
#include "ATI/atimgpud.h"

#pragma comment(lib, "nvapi")
#pragma comment(lib, "atimgpud_mtdll_x86")
#endif'''
GPU_VENDOR_HEADERS_NEW = b'''#if !defined(_EDITOR) && !defined(_WIN64)
#include "NVAPI/nvapi.h"
#include "ATI/atimgpud.h"

#pragma comment(lib, "nvapi")
#pragma comment(lib, "atimgpud_mtdll_x86")
#endif'''
GPU_VENDOR_CODE_OLD = b'''namespace
{
#ifndef _EDITOR
u32 GetNVGpuNum()'''
GPU_VENDOR_CODE_NEW = b'''namespace
{
#if !defined(_EDITOR) && !defined(_WIN64)
u32 GetNVGpuNum()'''


def native_newlines(data: bytes, replacement: bytes) -> bytes:
    if b"\r\n" in data[:2048]:
        return replacement.replace(b"\n", b"\r\n")
    return replacement


def replace_exact(path: Path, old: bytes, new: bytes, label: str, require_old_absent: bool = True) -> None:
    data = path.read_bytes()
    old = native_newlines(data, old)
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


def fix_xr3da_x64_dxsdk_link(root: Path) -> None:
    path = root / "xr_3da" / "XR_3DA.vcxproj"
    tree = ET.parse(path)
    project = tree.getroot()
    dxsdk_x64 = r"$(DXSDK_DIR)Lib\x64"
    x64_links = 0
    changed = 0

    for group in project.findall(Q("ItemDefinitionGroup")):
        if not is_x64_condition(group.get("Condition")):
            continue
        link = group.find(Q("Link"))
        if link is None:
            continue
        x64_links += 1
        dirs = link.find(Q("AdditionalLibraryDirectories"))
        current = dirs.text.strip() if dirs is not None and dirs.text else ""
        entries = [part.strip() for part in current.split(";") if part.strip()]
        if any(part.lower() == dxsdk_x64.lower() for part in entries):
            continue
        if dirs is None:
            dirs = ET.SubElement(link, Q("AdditionalLibraryDirectories"))
        tail = current or "%(AdditionalLibraryDirectories)"
        dirs.text = f"{dxsdk_x64};{tail}"
        changed += 1

    if x64_links == 0:
        raise RuntimeError("XR_3DA: no x64 Link configuration found for DirectX SDK repair")
    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)

    check = ET.parse(path).getroot()
    missing: list[str] = []
    checked = 0
    for group in check.findall(Q("ItemDefinitionGroup")):
        if not is_x64_condition(group.get("Condition")):
            continue
        link = group.find(Q("Link"))
        if link is None:
            continue
        checked += 1
        dirs = link.find(Q("AdditionalLibraryDirectories"))
        entries = [part.strip().lower() for part in ((dirs.text if dirs is not None and dirs.text else "").split(";")) if part.strip()]
        if dxsdk_x64.lower() not in entries:
            missing.append(group.get("Condition") or "<unknown>")
    if checked == 0 or missing:
        raise RuntimeError(f"XR_3DA: DirectX SDK x64 linker path missing from configurations: {missing}")

    print(f"[x64-dxsdk] XR_3DA x64 linker configs={checked} repaired={changed} path={dxsdk_x64}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted Win64 ABI/linkage fixes to X-Ray runtime sources.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    math_path = root / "xrCore" / "_math.cpp"
    core_path = root / "xrCore" / "xrCore.cpp"
    platform_path = root / "xrCore" / "xrCore_platform.h"
    xray_path = root / "xr_3da" / "x_ray.cpp"
    hwcaps_path = root / "xr_3da" / "HWCaps.cpp"
    lua_stub = root / "xrLua" / "src" / "ljit_x64_stub.c"
    lua_debug = root / "xrLua" / "src" / "ldebug.c"
    for path in (math_path, core_path, platform_path, xray_path, hwcaps_path, lua_stub, lua_debug):
        if not path.is_file():
            raise FileNotFoundError(path)

    fix_x64_linker_machine(root)
    fix_xrsound_x64_project(root)
    fix_xr3da_x64_dxsdk_link(root)

    replace_exact(math_path, RAISE_OLD, RAISE_NEW, "xrCore/_math.cpp RaiseException")
    print("[x64-abi] xrCore/_math.cpp: thread-name RaiseException payload migrated DWORD -> ULONG_PTR")

    replace_exact(core_path, APP_PATH_OLD, APP_PATH_NEW, "xrCore/xrCore.cpp g_application_path", require_old_absent=False)
    migrated = core_path.read_bytes()
    if b"#ifdef _WIN64" not in migrated or b"char g_application_path[256] = {};" not in migrated:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win64 storage definition was not installed")
    if migrated.count(APP_PATH_OLD) != 1:
        raise RuntimeError("xrCore/xrCore.cpp g_application_path: Win32 extern ownership was not preserved exactly once")
    print("[x64-abi] xrCore/xrCore.cpp: supplied Win64 g_application_path storage; Win32 keeps CrashHandler ownership")

    replace_exact(lua_stub, LUA_STUB_OLD, LUA_STUB_NEW, "xrLua/ljit_x64_stub.c LUA_CORE", require_old_absent=False)
    if lua_stub.read_bytes().count(b"#define LUA_CORE") != 1:
        raise RuntimeError("xrLua/ljit_x64_stub.c: LUA_CORE was not installed exactly once")
    print("[x64-abi] xrLua/src/ljit_x64_stub.c: x64 JIT stubs now export from xrLua instead of dllimport")

    replace_exact(lua_debug, CAST_INT_OLD, CAST_INT_NEW, "xrLua/ldebug.c currentpc cast")
    print("[x64-abi] xrLua/src/ldebug.c: removed undefined cast_int from Win64 currentpc fallback")

    replace_exact(platform_path, WINNT_OLD, WINNT_NEW, "xrCore/xrCore_platform.h _WIN32_WINNT")
    replace_exact(platform_path, SYSMETRICS_OLD, SYSMETRICS_NEW, "xrCore/xrCore_platform.h NOSYSMETRICS")
    print("[x64-winapi] xrCore/xrCore_platform.h: Windows 7 API level and system metrics declarations enabled")

    replace_exact(xray_path, DLGPROC_OLD, DLGPROC_NEW, "xr_3da/x_ray.cpp logDlgProc Win64 ABI")
    print("[x64-winapi] xr_3da/x_ray.cpp: logDlgProc return type migrated BOOL -> INT_PTR")

    replace_exact(hwcaps_path, GPU_VENDOR_HEADERS_OLD, GPU_VENDOR_HEADERS_NEW, "xr_3da/HWCaps.cpp vendor headers/link pragmas")
    replace_exact(hwcaps_path, GPU_VENDOR_CODE_OLD, GPU_VENDOR_CODE_NEW, "xr_3da/HWCaps.cpp vendor GPU-count implementation")
    migrated_hwcaps = hwcaps_path.read_bytes()
    if migrated_hwcaps.count(b"#if !defined(_EDITOR) && !defined(_WIN64)") != 2:
        raise RuntimeError("xr_3da/HWCaps.cpp: expected two Win64 exclusions for legacy vendor GPU-count code")
    if b'#pragma comment(lib, "nvapi")' not in migrated_hwcaps or b'#pragma comment(lib, "atimgpud_mtdll_x86")' not in migrated_hwcaps:
        raise RuntimeError("xr_3da/HWCaps.cpp: Win32 vendor link pragmas were not preserved")
    print("[x64-gpu-count] disabled legacy 32-bit NVAPI/ATI GPU-count libraries on Win64; Win32 behavior preserved")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
