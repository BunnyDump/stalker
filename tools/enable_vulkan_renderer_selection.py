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
        block = '''#ifndef DEDICATED_SERVER\n\tconst bool request_vulkan = strstr(Core.Params, "-vulkan") != 0;\n\tif (request_vulkan)\n\t{\n\t\tLog("Loading DLL:", vk_name);\n\t\thRender = LoadLibrary(vk_name);\n\t\tif (0 == hRender)\n\t\t{\n\t\t\tconst DWORD vk_error = GetLastError();\n\t\t\tMsg("...Vulkan renderer load failed (%lu); falling back to R2/R1.", (unsigned long)vk_error);\n\t\t}\n\t\telse\n\t\t{\n\t\t\ttypedef BOOL (__cdecl *xr_vk_probe_fn)();\n\t\t\ttypedef BOOL (__cdecl *xr_vk_activate_fn)();\n\t\t\txr_vk_probe_fn vk_probe = reinterpret_cast<xr_vk_probe_fn>(GetProcAddress(hRender, "xrRender_vk_capability_probe"));\n\t\t\txr_vk_activate_fn vk_activate = reinterpret_cast<xr_vk_activate_fn>(GetProcAddress(hRender, "xrRender_vk_activate"));\n\t\t\tconst BOOL vk_capable = vk_probe ? vk_probe() : FALSE;\n\t\t\tconst BOOL vk_activated = (vk_capable && vk_activate) ? vk_activate() : FALSE;\n\t\t\tif (!vk_capable || !vk_activated)\n\t\t\t{\n\t\t\t\tMsg("...Vulkan capability/activation handshake failed; unloading xrRender_VK and falling back to R2/R1.");\n\t\t\t\tFreeLibrary(hRender);\n\t\t\t\thRender = 0;\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\t// xrRender_VK is an R2-compatible backend from the engine/game point of view.\n\t\t\t\tpsDeviceFlags.set(rsR2, TRUE);\n\t\t\t\trenderer_value = 1;\n\t\t\t\tMsg("* Vulkan renderer selected and capability-validated: %s", vk_name);\n\t\t\t}\n\t\t}\n\t}\n\n\tif (0 == hRender && psDeviceFlags.test(rsR2))\n'''
        if marker in text:
            text = text.replace(marker, block, 1)
        else:
            # The RC6 integration patch already contains an older DXVK bridge
            # selection block. Replace that whole pre-R2 section instead of
            # requiring the pristine upstream marker.
            bridge_marker = '''#ifndef DEDICATED_SERVER
\tif (g_vulkan_backend)
'''
            r2_marker = '''\tif (0 == hRender && psDeviceFlags.test(rsR2))
'''
            bridge_start = text.find(bridge_marker)
            r2_start = text.find(r2_marker, bridge_start + len(bridge_marker))
            if bridge_start < 0 or r2_start < 0:
                raise RuntimeError("Vulkan renderer selection: upstream/RC6 R2 load marker missing")
            text = text[:bridge_start] + block + text[r2_start + len(r2_marker):]

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        'LPCSTR vk_name = "xrRender_VK.dll";',
        'strstr(Core.Params, "-vulkan")',
        'hRender = LoadLibrary(vk_name);',
        'GetProcAddress(hRender, "xrRender_vk_capability_probe")',
        'GetProcAddress(hRender, "xrRender_vk_activate")',
        'const BOOL vk_capable = vk_probe ? vk_probe() : FALSE;',
        'const BOOL vk_activated = (vk_capable && vk_activate) ? vk_activate() : FALSE;',
        'FreeLibrary(hRender);',
        'hRender = 0;',
        'if (0 == hRender && psDeviceFlags.test(rsR2))',
        'falling back to R2/R1',
        'psDeviceFlags.set(rsR2, TRUE);',
        'renderer_value = 1;',
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan renderer selection validation failed: missing {token}")
    vk_load = final.find('hRender = LoadLibrary(vk_name);')
    probe = final.find('GetProcAddress(hRender, "xrRender_vk_capability_probe")', vk_load)
    activate = final.find('GetProcAddress(hRender, "xrRender_vk_activate")', probe)
    unload = final.find('FreeLibrary(hRender);', activate)
    # RC6 may retain a native-D3D9 fallback ternary around this call.
    r2_load = final.find('LoadLibrary(r2_name)', unload)
    if min(vk_load, probe, activate, unload, r2_load) < 0 or not vk_load < probe < activate < unload < r2_load:
        raise RuntimeError("Vulkan renderer selection validation failed: post-load handshake/fallback order invalid")
    print("[vulkan-selection] -vulkan performs post-load capability + activation handshake, then R2/R1 fallback on failure")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add explicit capability-validated Vulkan renderer selection to X-Ray EngineAPI.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
