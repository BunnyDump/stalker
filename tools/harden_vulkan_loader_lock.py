from __future__ import annotations

import argparse
import re
from pathlib import Path


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
    unsafe = re.compile(
        r"\s*if\s*\(\s*!\s*xrRender_test_hw\s*\(\s*\)\s*\)\s*"
        r"return\s+FALSE\s*;",
        flags=re.DOTALL,
    )
    if unsafe.search(body):
        safe_body = unsafe.sub("\n\t\t// Vulkan probing is intentionally deferred until the renderer owns a real HWND.\n", body, count=1)
        text = text[: attach_match.start("body")] + safe_body + text[attach_match.end("body") :]
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
        "xrRender_test_hw(",
        "xr_vk_bootstrap_",
        "LoadLibrary(",
        "LoadLibraryA(",
        "LoadLibraryW(",
        "FreeLibrary(",
    )
    for token in forbidden:
        if token in final_body:
            raise RuntimeError(f"Vulkan loader-lock hardening validation: unsafe token in DllMain attach: {token}")
    for token in ("::Render = &RImplementation", "xrRender_initconsole()"):
        if token not in final_body:
            raise RuntimeError(f"Vulkan loader-lock hardening validation: missing renderer ABI binding: {token}")

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

    print("[vulkan-loader-lock] DllMain is bootstrap-free; Vulkan initialization is deferred to HWND attach")


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Vulkan loader/bootstrap work out of Windows DllMain loader lock.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
