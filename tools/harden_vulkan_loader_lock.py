from __future__ import annotations

import argparse
import re
from pathlib import Path

ACTIVATE_IMPL = r'''
extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_activate()
{
    ::Render = &RImplementation;
    xrRender_initconsole();
    return TRUE;
}

'''


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    entry = renderer / "xrRender_R2.cpp"
    if not entry.is_file():
        raise FileNotFoundError(entry)

    text = entry.read_text(encoding="utf-8", errors="ignore")
    attach_match = re.search(
        r"case\s+DLL_PROCESS_ATTACH\s*:\s*(?P<body>.*?)(?=\s*break\s*;)",
        text,
        flags=re.DOTALL,
    )
    if not attach_match:
        raise RuntimeError("Vulkan loader-lock hardening: DLL_PROCESS_ATTACH block not found")

    body = attach_match.group("body")
    if any(token in body for token in ("xrRender_test_hw", "::Render = &RImplementation", "xrRender_initconsole")):
        safe_body = "\n\t\t// No Vulkan probing or renderer registration under the Windows loader lock.\n\t\t// EngineAPI performs capability probing and explicit activation after LoadLibrary returns.\n"
        text = text[: attach_match.start("body")] + safe_body + text[attach_match.end("body") :]

    if "xrRender_vk_activate()" not in text:
        insert = text.find("BOOL APIENTRY DllMain")
        if insert < 0:
            raise RuntimeError("Vulkan loader-lock hardening: DllMain marker missing")
        text = text[:insert] + ACTIVATE_IMPL + text[insert:]

    entry.write_text(text, encoding="utf-8")
    final = entry.read_text(encoding="utf-8", errors="ignore")
    final_attach = re.search(
        r"case\s+DLL_PROCESS_ATTACH\s*:\s*(?P<body>.*?)(?=\s*break\s*;)",
        final,
        flags=re.DOTALL,
    )
    if not final_attach:
        raise RuntimeError("Vulkan loader-lock hardening validation: DLL_PROCESS_ATTACH block missing")
    final_body = final_attach.group("body")
    forbidden = (
        "xrRender_test_hw",
        "xrRender_vk_activate",
        "::Render = &RImplementation",
        "xrRender_initconsole",
        "xr_vk_bootstrap_",
        "LoadLibrary(",
        "LoadLibraryA(",
        "LoadLibraryW(",
        "FreeLibrary(",
    )
    for token in forbidden:
        if token in final_body:
            raise RuntimeError(f"Vulkan loader-lock hardening validation: side effect remains in DllMain attach: {token}")

    activate = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_activate()')
    bind = final.find("::Render = &RImplementation", activate)
    console = final.find("xrRender_initconsole()", bind)
    return_true = final.find("return TRUE;", console)
    if min(activate, bind, console, return_true) < 0 or not activate < bind < console < return_true:
        raise RuntimeError("Vulkan loader-lock hardening validation: post-load renderer activation export incomplete")

    lifecycle = renderer / "r2.cpp"
    if not lifecycle.is_file():
        raise FileNotFoundError(lifecycle)
    lifecycle_text = lifecycle.read_text(encoding="utf-8", errors="ignore")
    if "xr_vk_bootstrap_attach_window(Device.m_hWnd, Device.dwWidth, Device.dwHeight)" not in lifecycle_text:
        raise RuntimeError("Vulkan loader-lock hardening validation: deferred HWND bootstrap hook missing")

    bootstrap = renderer / "vk_bootstrap.cpp"
    if not bootstrap.is_file():
        raise FileNotFoundError(bootstrap)
    bootstrap_text = bootstrap.read_text(encoding="utf-8", errors="ignore")
    if "if (!window_handle || !xr_vk_bootstrap_initialize())" not in bootstrap_text:
        raise RuntimeError("Vulkan loader-lock hardening validation: attach_window is not the lazy bootstrap boundary")

    print("[vulkan-loader-lock] DllMain is side-effect-free; renderer activation is an explicit post-load export")


def main() -> int:
    parser = argparse.ArgumentParser(description="Move Vulkan probing and renderer registration outside Windows DllMain loader lock.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
