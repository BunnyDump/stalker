from __future__ import annotations

import argparse
from pathlib import Path


def install(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "EngineAPI.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    if 'LPCSTR vk_name = "xrRender_VK.dll";' in text:
        return

    name_marker = '\tLPCSTR r1_name = "xrRender_R1.dll";\n\tLPCSTR r2_name = "xrRender_R2.dll";\n'
    name_block = name_marker + '\tLPCSTR vk_name = "xrRender_VK.dll";\n'
    if name_marker not in text:
        raise RuntimeError("Vulkan engine loader name marker not found")
    text = text.replace(name_marker, name_block, 1)

    old_block = '''#ifndef DEDICATED_SERVER
\tif (psDeviceFlags.test(rsR2))
\t{
\t\t// try to initialize R2
\t\tLog("Loading DLL:", r2_name);
\t\thRender = LoadLibrary(r2_name);
\t\tif (0 == hRender)
\t\t{
\t\t\t// try to load R1
\t\t\tMsg("...Failed - incompatible hardware.");
\t\t}
\t}
#endif
'''
    new_block = '''#ifndef DEDICATED_SERVER
\tconst bool request_vulkan = strstr(Core.Params, "-vulkan") != 0 || strstr(Core.Params, "-renderer_vk") != 0;
\tif (request_vulkan)
\t{
\t\tLog("Loading DLL:", vk_name);
\t\thRender = LoadLibrary(vk_name);
\t\tif (0 == hRender)
\t\t\tMsg("...Vulkan renderer unavailable, falling back to R2/R1.");
\t\telse
\t\t{
\t\t\tpsDeviceFlags.set(rsR2, TRUE);
\t\t\trenderer_value = 1;
\t\t}
\t}
\n\tif (0 == hRender && psDeviceFlags.test(rsR2))
\t{
\t\t// transitional R2 fallback while native Vulkan migration remains in progress
\t\tLog("Loading DLL:", r2_name);
\t\thRender = LoadLibrary(r2_name);
\t\tif (0 == hRender)
\t\t\tMsg("...Failed - incompatible hardware.");
\t}
#endif
'''
    if old_block not in text:
        raise RuntimeError("Vulkan engine loader render-selection marker not found")
    text = text.replace(old_block, new_block, 1)
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    for token in ('xrRender_VK.dll', 'request_vulkan', '-renderer_vk', 'falling back to R2/R1'):
        if token not in final:
            raise RuntimeError(f"Vulkan engine loader validation missing {token}")
    if final.find('LoadLibrary(vk_name)') > final.find('LoadLibrary(r2_name)'):
        raise RuntimeError("Vulkan renderer is not attempted before R2 fallback")
    print("[vulkan-engine-loader] explicit -vulkan/-renderer_vk path installed before R2/R1 fallback")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install explicit native Vulkan renderer selection in X-Ray EngineAPI.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
