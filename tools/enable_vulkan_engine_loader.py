from __future__ import annotations

import argparse
import re
from pathlib import Path


def install(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "EngineAPI.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"

    # The cumulative RC6 patch already introduced vk_name and a temporary
    # DXVK bridge selector. Replace that selector with a direct native
    # xrRender_VK load, while retaining the verified native-D3D9 fallback.
    if 'LPCSTR vk_name = "xrRender_VK.dll";' not in text:
        name_pattern = r'(\tLPCSTR r1_name = "xrRender_R1\.dll";\r?\n\tLPCSTR r2_name = "xrRender_R2\.dll";\r?\n)'
        text, count = re.subn(name_pattern, r'\1\tLPCSTR vk_name = "xrRender_VK.dll";' + newline, text, count=1)
        if count != 1:
            raise RuntimeError("Vulkan engine loader DLL-name marker not found")

    start = text.find("#ifndef DEDICATED_SERVER", text.find('LPCSTR vk_name = "xrRender_VK.dll";'))
    end = text.find("#endif", start)
    if start < 0 or end < 0:
        raise RuntimeError("Vulkan engine loader render-selection block not found")
    end += len("#endif")

    old_block = text[start:end]
    if "r2_name" not in old_block or "hRender" not in old_block:
        raise RuntimeError("Vulkan engine loader found an unexpected render-selection block")

    bridge_mode = "xr_vulkan_bridge_available()" in old_block or "g_vulkan_backend" in old_block
    if bridge_mode and "force_native_d3d9_fallback" not in text:
        raise RuntimeError("RC6 bridge fallback helper state is missing")

    new_block = (
        "#ifndef DEDICATED_SERVER" + newline +
        '\tconst bool request_vulkan = g_vulkan_backend || strstr(Core.Params, "-vulkan") != 0 || strstr(Core.Params, "-renderer_vk") != 0;' + newline +
        "\tif (request_vulkan)" + newline +
        "\t{" + newline +
        '\t\tLog("Loading DLL:", vk_name);' + newline +
        "\t\thRender = LoadLibraryA(vk_name);" + newline +
        "\t\tif (0 == hRender)" + newline +
        "\t\t{" + newline +
        '\t\t\tMsg("! Native Vulkan renderer unavailable, falling back to native Direct3D 9 R2.");' + newline +
        "\t\t\tg_vulkan_backend = FALSE;" + newline +
        "\t\t\trenderer_value = 2;" + newline +
        "\t\t\tforce_native_d3d9_fallback = true;" + newline +
        "\t\t}" + newline +
        "\t\telse" + newline +
        "\t\t{" + newline +
        "\t\t\tg_vulkan_backend = TRUE;" + newline +
        "\t\t\tpsDeviceFlags.set(rsR2, TRUE);" + newline +
        "\t\t\trenderer_value = 1;" + newline +
        "\t\t}" + newline +
        "\t}" + newline + newline +
        "\tif (0 == hRender && psDeviceFlags.test(rsR2))" + newline +
        "\t{" + newline +
        '\t\tLog("Loading DLL:", r2_name);' + newline +
        "\t\thRender = force_native_d3d9_fallback ? xr_load_renderer_with_native_d3d9(r2_name) : LoadLibraryA(r2_name);" + newline +
        "\t\tif (0 == hRender)" + newline +
        '\t\t\tMsg("...Failed - incompatible hardware.");' + newline +
        "\t}" + newline +
        "#endif"
    )
    text = text[:start] + new_block + text[end:]
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    for token in ('xrRender_VK.dll', 'request_vulkan', 'LoadLibraryA(vk_name)', '-renderer_vk', 'force_native_d3d9_fallback'):
        if token not in final:
            raise RuntimeError(f"Vulkan engine loader validation missing {token}")
    init_start = final.find("void CEngineAPI::Initialize(void)")
    vk_load = final.find("LoadLibraryA(vk_name)", init_start)
    r2_load = final.find("r2_name", vk_load + 1)
    if vk_load < 0 or r2_load < 0 or vk_load > r2_load:
        raise RuntimeError("Native Vulkan renderer is not attempted before R2 fallback")
    init_end = final.find("// game", init_start)
    if "xr_vulkan_bridge_available()" in final[init_start:init_end]:
        raise RuntimeError("Legacy DXVK bridge selection remains active in EngineAPI::Initialize")
    print("[vulkan-engine-loader] native xrRender_VK selection replaces temporary DXVK bridge path")


def main() -> int:
    ap = argparse.ArgumentParser(description="Install explicit native Vulkan renderer selection in X-Ray EngineAPI.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    install(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
