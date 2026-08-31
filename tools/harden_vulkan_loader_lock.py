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

    legacy_present_gate = 'xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent")'
    if legacy_present_gate in lifecycle_text:
        lifecycle_text = lifecycle_text.replace(legacy_present_gate, "xr_vk_bootstrap_runtime_ready()", 1)
        lifecycle.write_text(lifecycle_text, encoding="utf-8")
    lifecycle_text = lifecycle.read_text(encoding="utf-8", errors="ignore")
    if 'strstr(Core.Params, "-vkpresent")' in lifecycle_text:
        raise RuntimeError("Vulkan present activation validation: obsolete -vkpresent gate remains")

    frame_start = lifecycle_text.find("void CRender::OnFrame()")
    if frame_start < 0:
        raise RuntimeError("Vulkan present activation validation: CRender::OnFrame missing")
    frame_end = lifecycle_text.find("// Implementation", frame_start)
    if frame_end < 0:
        frame_end = frame_start + 1800
    frame = lifecycle_text[frame_start:frame_end]
    ready = frame.find("xr_vk_bootstrap_runtime_ready()")
    present = frame.find("xr_vk_bootstrap_frame();", ready)
    if ready < 0 or present < 0 or ready >= present:
        raise RuntimeError("Vulkan present activation validation: ready-gated frame present hook missing")

    bootstrap = renderer / "vk_bootstrap.cpp"
    if not bootstrap.is_file():
        raise FileNotFoundError(bootstrap)
    bootstrap_text = bootstrap.read_text(encoding="utf-8", errors="ignore")
    if "if (!window_handle || !xr_vk_bootstrap_initialize())" not in bootstrap_text:
        raise RuntimeError("Vulkan loader-lock hardening validation: attach_window is not the lazy bootstrap boundary")

    print("[vulkan-startup] DllMain is bootstrap-free; initialization is deferred to HWND attach; runtime-ready Vulkan present is active")


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Vulkan bootstrap outside DllMain and make runtime readiness drive presentation.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
