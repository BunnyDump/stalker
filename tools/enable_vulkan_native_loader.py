from __future__ import annotations

import argparse
import re
from pathlib import Path


def patch_engine_api(root: Path) -> None:
    path = root / "xr_3da" / "EngineAPI.cpp"
    text = path.read_text(encoding="utf-8")

    start = text.find("bool xr_file_exists(LPCSTR path)")
    end_marker = "\n}\n}\n\n//////////////////////////////////////////////////////////////////////\n// Construction/Destruction"
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("native Vulkan loader: EngineAPI bridge helper block not found")

    replacement = r'''bool xr_vulkan_native_loader_available()
{
    HMODULE vulkan = LoadLibraryA("vulkan-1.dll");
    if (!vulkan)
    {
        Msg("! Vulkan loader not found (vulkan-1.dll). Update/install the GPU driver.");
        return false;
    }

    const bool has_entry = GetProcAddress(vulkan, "vkGetInstanceProcAddr") != NULL;
    FreeLibrary(vulkan);
    if (!has_entry)
    {
        Msg("! Vulkan loader is invalid: vkGetInstanceProcAddr is missing.");
        return false;
    }

    Msg("* Native Vulkan loader detected; xrRender_VK will initialize Vulkan directly.");
    return true;
}
'''
    text = text[:start] + replacement + text[end + len("\n}\n") :]

    text = text.replace("bool force_native_d3d9_fallback = false;", "bool vulkan_load_failed = false;")
    text = text.replace("if (xr_vulkan_bridge_available())", "if (xr_vulkan_native_loader_available())")
    text = text.replace("Log(\"Loading Vulkan bridge renderer DLL:\", vk_name);", "Log(\"Loading native Vulkan renderer DLL:\", vk_name);")
    text = text.replace(
        'Msg("! Vulkan renderer unavailable, falling back to native Direct3D 9 R2.");\n\t\t\tg_vulkan_backend = FALSE;\n\t\t\trenderer_value = 2;\n\t\t\tforce_native_d3d9_fallback = true;',
        'Msg("! Native Vulkan renderer unavailable, falling back to Direct3D 9 R2.");\n\t\t\tg_vulkan_backend = FALSE;\n\t\t\trenderer_value = 2;\n\t\t\tvulkan_load_failed = true;')
    text = text.replace(
        "hRender = force_native_d3d9_fallback ? xr_load_renderer_with_native_d3d9(r2_name) : LoadLibrary(r2_name);",
        "hRender = LoadLibrary(r2_name);")
    text = text.replace(
        "hRender = force_native_d3d9_fallback ? xr_load_renderer_with_native_d3d9(r1_name) : LoadLibrary(r1_name);",
        "hRender = LoadLibrary(r1_name);")
    text = text.replace("bool vulkan_load_failed = false;\n", "")

    forbidden = ("DXVK", "xr_vulkan_bridge_available", "xr_load_renderer_with_native_d3d9", "local D3D9", "D3D9-to-Vulkan")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"native Vulkan loader cleanup failed: legacy bridge token remains: {token}")
    if "xr_vulkan_native_loader_available()" not in text or "Loading native Vulkan renderer DLL" not in text:
        raise RuntimeError("native Vulkan loader validation failed")
    path.write_text(text, encoding="utf-8")


def patch_renderer_entry(root: Path) -> None:
    renderer = root / "xr_3da" / "xrRender_VK"
    candidates = [renderer / "xrRender_VK.cpp", renderer / "xrRender_R2.cpp"]
    changed = False
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "xrRender_test_hw()" in text:
            text = re.sub(
                r'\s*// Hardware capability probing[^\n]*\n\s*//[^\n]*\n\s*if \(!xrRender_test_hw\(\)\)\s*\n\s*return FALSE;\s*\n',
                "\n",
                text,
                count=1,
            )
            if "xrRender_test_hw()" in text:
                text = text.replace("\t\tif (!xrRender_test_hw())\n\t\t\treturn FALSE;\n", "")
            path.write_text(text, encoding="utf-8")
            changed = True
    if not changed:
        raise RuntimeError("native Vulkan loader: renderer DllMain hardware-probe call not found")
    for path in candidates:
        if path.is_file() and "xrRender_test_hw()" in path.read_text(encoding="utf-8", errors="ignore"):
            raise RuntimeError(f"native Vulkan loader: transitive Vulkan probe remains in DllMain source {path.name}")


def enable_native_loader(root: Path) -> None:
    root = root.resolve()
    patch_engine_api(root)
    patch_renderer_entry(root)
    print("[vulkan-native-loader] DXVK/local-d3d9 bridge requirement removed; DllMain no longer performs Vulkan probing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove the transitional DXVK bridge and loader-lock Vulkan probe from RC6.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable_native_loader(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
