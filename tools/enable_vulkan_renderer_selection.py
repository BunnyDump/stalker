from __future__ import annotations

import argparse
from pathlib import Path


def enable(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "EngineAPI.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    if 'LPCSTR vk_name = "xrRender_VK.dll";' not in text:
        old_names = '''\tLPCSTR r1_name = "xrRender_R1.dll";\n\tLPCSTR r2_name = "xrRender_R2.dll";\n'''
        new_names = old_names + '\tLPCSTR vk_name = "xrRender_VK.dll";\n'
        if old_names not in text:
            raise RuntimeError("Vulkan renderer selection: renderer DLL marker missing")
        text = text.replace(old_names, new_names, 1)

    if 'const bool request_vulkan = strstr(Core.Params, "-vulkan") != 0;' not in text:
        marker = '''#ifndef DEDICATED_SERVER\n\tif (psDeviceFlags.test(rsR2))\n'''
        block = '''#ifndef DEDICATED_SERVER\n\tconst bool request_vulkan = strstr(Core.Params, "-vulkan") != 0;\n\tif (request_vulkan)\n\t{\n\t\tLog("Loading DLL:", vk_name);\n\t\thRender = LoadLibrary(vk_name);\n\t\tif (0 == hRender)\n\t\t{\n\t\t\tconst DWORD vk_error = GetLastError();\n\t\t\tMsg("...Vulkan renderer load failed (%lu); falling back to R2/R1.", (unsigned long)vk_error);\n\t\t}\n\t\telse\n\t\t{\n\t\t\t// xrRender_VK is an R2-compatible backend from the engine/game point of view.\n\t\t\tpsDeviceFlags.set(rsR2, TRUE);\n\t\t\trenderer_value = 1;\n\t\t\tMsg("* Vulkan renderer selected: %s", vk_name);\n\t\t}\n\t}\n\n\tif (0 == hRender && psDeviceFlags.test(rsR2))\n'''
        if marker not in text:
            raise RuntimeError("Vulkan renderer selection: R2 load marker missing")
        text = text.replace(marker, block, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        'LPCSTR vk_name = "xrRender_VK.dll";',
        'strstr(Core.Params, "-vulkan")',
        'hRender = LoadLibrary(vk_name);',
        'if (0 == hRender && psDeviceFlags.test(rsR2))',
        'falling back to R2/R1',
        'psDeviceFlags.set(rsR2, TRUE);',
        'renderer_value = 1;',
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan renderer selection validation failed: missing {token}")
    if final.find('hRender = LoadLibrary(vk_name);') > final.find('hRender = LoadLibrary(r2_name);'):
        raise RuntimeError("Vulkan renderer selection validation failed: Vulkan must be attempted before R2")
    print("[vulkan-selection] -vulkan selects xrRender_VK.dll with R2 then R1 fallback")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add explicit Vulkan renderer selection to X-Ray EngineAPI.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
