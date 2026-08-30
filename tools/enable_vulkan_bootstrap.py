from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", MSBUILD_NS)
Q = lambda name: f"{{{MSBUILD_NS}}}{name}"

HEADER = r'''#pragma once

bool xr_vk_bootstrap_initialize();
void xr_vk_bootstrap_shutdown();
unsigned xr_vk_bootstrap_physical_device_count();
'''

SOURCE = r'''#include "stdafx.h"
#define VK_NO_PROTOTYPES
#include "../../third-party/include/x64/vulkan/vulkan.h"
#include "vk_bootstrap.h"
#include <windows.h>

namespace
{
    HMODULE g_vulkan_loader = NULL;
    VkInstance g_vulkan_instance = VK_NULL_HANDLE;
    PFN_vkGetInstanceProcAddr g_vkGetInstanceProcAddr = NULL;
    PFN_vkDestroyInstance g_vkDestroyInstance = NULL;
    unsigned g_physical_device_count = 0;

    void xr_vk_bootstrap_reset()
    {
        g_vulkan_instance = VK_NULL_HANDLE;
        g_vkGetInstanceProcAddr = NULL;
        g_vkDestroyInstance = NULL;
        g_physical_device_count = 0;
        if (g_vulkan_loader)
        {
            FreeLibrary(g_vulkan_loader);
            g_vulkan_loader = NULL;
        }
    }
}

bool xr_vk_bootstrap_initialize()
{
    if (g_vulkan_instance != VK_NULL_HANDLE)
        return true;

    g_vulkan_loader = LoadLibraryA("vulkan-1.dll");
    if (!g_vulkan_loader)
        return false;

    g_vkGetInstanceProcAddr = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
        GetProcAddress(g_vulkan_loader, "vkGetInstanceProcAddr"));
    if (!g_vkGetInstanceProcAddr)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    PFN_vkCreateInstance create_instance = reinterpret_cast<PFN_vkCreateInstance>(
        g_vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance"));
    if (!create_instance)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    VkApplicationInfo app_info = {};
    app_info.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app_info.pApplicationName = "S.T.A.L.K.E.R. X-Ray RC6";
    app_info.applicationVersion = VK_MAKE_VERSION(0, 6, 0);
    app_info.pEngineName = "X-Ray Engine";
    app_info.engineVersion = VK_MAKE_VERSION(0, 6, 0);
    app_info.apiVersion = VK_API_VERSION_1_0;

    VkInstanceCreateInfo instance_info = {};
    instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    instance_info.pApplicationInfo = &app_info;

    if (create_instance(&instance_info, NULL, &g_vulkan_instance) != VK_SUCCESS)
    {
        xr_vk_bootstrap_reset();
        return false;
    }

    g_vkDestroyInstance = reinterpret_cast<PFN_vkDestroyInstance>(
        g_vkGetInstanceProcAddr(g_vulkan_instance, "vkDestroyInstance"));
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices =
        reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(
            g_vkGetInstanceProcAddr(g_vulkan_instance, "vkEnumeratePhysicalDevices"));

    if (!g_vkDestroyInstance || !enumerate_physical_devices ||
        enumerate_physical_devices(g_vulkan_instance, &g_physical_device_count, NULL) != VK_SUCCESS ||
        g_physical_device_count == 0)
    {
        xr_vk_bootstrap_shutdown();
        return false;
    }

    OutputDebugStringA("[X-Ray Vulkan] VkInstance initialized; physical device detected.\n");
    return true;
}

void xr_vk_bootstrap_shutdown()
{
    if (g_vulkan_instance != VK_NULL_HANDLE && g_vkDestroyInstance)
        g_vkDestroyInstance(g_vulkan_instance, NULL);
    xr_vk_bootstrap_reset();
}

unsigned xr_vk_bootstrap_physical_device_count()
{
    return g_physical_device_count;
}
'''


def patch_dependency_script(root: Path) -> None:
    path = root / "PREPARE_RC6_X64_DEPS.ps1"
    text = path.read_text(encoding="utf-8-sig")
    old = '"dependencies": ["libogg", "libvorbis", "libtheora"]'
    new = '"dependencies": ["libogg", "libvorbis", "libtheora", "vulkan-headers"]'
    if new not in text:
        if old not in text:
            raise RuntimeError("Vulkan bootstrap: Xiph vcpkg manifest dependency list not found")
        text = text.replace(old, new, 1)

    marker = "# OpenAL Soft x64 replaces the legacy 32-bit Router/wrap_oal pair."
    copy_block = """# Vulkan headers are used by xrRender_VK while the loader is resolved dynamically at runtime.\n$vulkanHeaders=Join-Path $inst 'include\\vulkan'\n$vulkanVideoHeaders=Join-Path $inst 'include\\vk_video'\nif(-not (Test-Path $vulkanHeaders)){ throw 'vcpkg vulkan-headers include directory not found.' }\nif(-not (Test-Path $vulkanVideoHeaders)){ throw 'vcpkg vulkan video headers include directory not found.' }\nCopy-Item -Recurse -Force $vulkanHeaders $incDst\nCopy-Item -Recurse -Force $vulkanVideoHeaders $incDst\n"""
    if copy_block not in text:
        if marker not in text:
            raise RuntimeError("Vulkan bootstrap: OpenAL marker not found in dependency script")
        text = text.replace(marker, copy_block + marker, 1)

    path.write_text(text, encoding="utf-8")
    print("[vulkan-deps] vulkan-headers + vk_video headers added to RC6 vcpkg dependency preparation")


def patch_renderer_project(renderer: Path) -> None:
    project_path = renderer / "xrRender_VK.vcxproj"
    if not project_path.is_file():
        raise FileNotFoundError(project_path)
    tree = ET.parse(project_path)
    root = tree.getroot()

    compile_exists = any((node.get("Include") or "").lower() == "vk_bootstrap.cpp" for node in root.findall(f".//{Q('ClCompile')}"))
    include_exists = any((node.get("Include") or "").lower() == "vk_bootstrap.h" for node in root.findall(f".//{Q('ClInclude')}"))

    groups = root.findall(Q("ItemGroup"))
    compile_group = next((g for g in groups if g.find(Q("ClCompile")) is not None), None)
    include_group = next((g for g in groups if g.find(Q("ClInclude")) is not None), None)
    if compile_group is None or include_group is None:
        raise RuntimeError("Vulkan bootstrap: unable to locate compile/include ItemGroups")
    if not compile_exists:
        ET.SubElement(compile_group, Q("ClCompile"), {"Include": "vk_bootstrap.cpp"})
    if not include_exists:
        ET.SubElement(include_group, Q("ClInclude"), {"Include": "vk_bootstrap.h"})
    tree.write(project_path, encoding="utf-8", xml_declaration=True)
    print("[vulkan-project] vk_bootstrap.cpp/.h added to xrRender_VK.vcxproj")


def patch_renderer_lifecycle(renderer: Path) -> None:
    source = renderer / "r2.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8-sig", errors="strict")
    newline = "\r\n" if "\r\n" in text else "\n"

    if '#include "vk_bootstrap.h"' not in text:
        match = re.search(r'(#include\s+"r2\.h"\s*\r?\n)', text)
        if not match:
            raise RuntimeError("Vulkan bootstrap: r2.h include not found in renderer lifecycle source")
        text = text[:match.end()] + '#include "vk_bootstrap.h"' + newline + text[match.end():]

    if "xr_vk_bootstrap_initialize()" not in text:
        pattern = r'(void\s+CRender::create\(\)\s*\r?\n\{\s*\r?\n)'
        replacement = (
            r'\1' +
            '\tif (!xr_vk_bootstrap_initialize())' + newline +
            '\t\tMsg("! [X-Ray Vulkan] Native Vulkan bootstrap unavailable; transitional renderer path remains active.");' + newline + newline
        )
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError("Vulkan bootstrap: CRender::create lifecycle hook not found")

    if "xr_vk_bootstrap_shutdown();" not in text:
        marker = '\tDevice.seqFrame.Remove(this);' + newline
        if marker not in text:
            raise RuntimeError("Vulkan bootstrap: CRender::destroy shutdown marker not found")
        text = text.replace(
            marker,
            marker + '\txr_vk_bootstrap_shutdown();' + newline,
            1,
        )

    source.write_text(text, encoding="utf-8")
    print("[vulkan-lifecycle] native Vulkan bootstrap moved out of DllMain into CRender::create/destroy")


def enable_vulkan_bootstrap(root: Path) -> None:
    root = root.resolve()
    renderer = root / "xr_3da" / "xrRender_VK"
    if not renderer.is_dir():
        raise FileNotFoundError(renderer)
    patch_dependency_script(root)
    (renderer / "vk_bootstrap.h").write_text(HEADER, encoding="utf-8")
    (renderer / "vk_bootstrap.cpp").write_text(SOURCE, encoding="utf-8")
    patch_renderer_project(renderer)
    patch_renderer_lifecycle(renderer)

    project_text = (renderer / "xrRender_VK.vcxproj").read_text(encoding="utf-8", errors="ignore")
    if "vk_bootstrap.cpp" not in project_text:
        raise RuntimeError("Vulkan bootstrap validation: source is absent from project")

    source_text = (renderer / "vk_bootstrap.cpp").read_text(encoding="utf-8")
    for token in ("VkInstance", "vkCreateInstance", "vkEnumeratePhysicalDevices", "vulkan-1.dll"):
        if token not in source_text:
            raise RuntimeError(f"Vulkan bootstrap validation: missing {token}")

    lifecycle_text = (renderer / "r2.cpp").read_text(encoding="utf-8", errors="ignore")
    if lifecycle_text.count("xr_vk_bootstrap_initialize()") != 1:
        raise RuntimeError("Vulkan bootstrap validation: expected one CRender::create initialization hook")
    if lifecycle_text.count("xr_vk_bootstrap_shutdown();") != 1:
        raise RuntimeError("Vulkan bootstrap validation: expected one CRender::destroy shutdown hook")

    entry_candidates = [renderer / "xrRender_VK.cpp", renderer / "xrRender_R2.cpp"]
    entry = next((p for p in entry_candidates if p.is_file()), None)
    if entry is None:
        raise RuntimeError("Vulkan bootstrap validation: renderer DLL entry source not found")
    entry_text = entry.read_text(encoding="utf-8", errors="ignore")
    if "xr_vk_bootstrap_initialize" in entry_text or "xr_vk_bootstrap_shutdown" in entry_text:
        raise RuntimeError("Vulkan bootstrap validation: Vulkan API must not run from DllMain")

    print("[vulkan-bootstrap] native loader + VkInstance + physical-device enumeration installed outside loader lock")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the first native Vulkan bootstrap into materialized xrRender_VK.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable_vulkan_bootstrap(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
