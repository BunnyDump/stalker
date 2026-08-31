from __future__ import annotations

import argparse
import re
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    engine_api = root / "xr_3da" / "EngineAPI.cpp"
    renderer = root / "xr_3da" / "xrRender_VK"
    dll_entry = renderer / "xrRender_R2.cpp"
    lifecycle = renderer / "r2.cpp"
    render = renderer / "r2_R_render.cpp"
    bootstrap = renderer / "vk_bootstrap.cpp"
    for path in (engine_api, dll_entry, lifecycle, render, bootstrap):
        if not path.is_file():
            raise FileNotFoundError(path)

    engine = engine_api.read_text(encoding="utf-8", errors="ignore")
    for token in ('"xrRender_VK.dll"', 'strstr(Core.Params, "-vulkan")', "LoadLibrary(vk_name)"):
        if token not in engine:
            raise RuntimeError(f"Vulkan startup validation: engine selection path missing {token}")
    vk_select = engine.find('strstr(Core.Params, "-vulkan")')
    vk_load = engine.find("LoadLibrary(vk_name)", vk_select)
    r2_load = engine.find("LoadLibrary(r2_name)", vk_load)
    r1_load = engine.find("LoadLibrary(r1_name)", r2_load)
    if min(vk_select, vk_load, r2_load, r1_load) < 0 or not vk_select < vk_load < r2_load < r1_load:
        raise RuntimeError("Vulkan startup validation: Vulkan -> R2 -> R1 load/fallback order invalid")

    entry = dll_entry.read_text(encoding="utf-8", errors="ignore")
    attach = re.search(
        r"case\s+DLL_PROCESS_ATTACH\s*:\s*(?P<body>.*?)(?=\s*break\s*;)",
        entry,
        flags=re.DOTALL,
    )
    if not attach:
        raise RuntimeError("Vulkan startup validation: DLL_PROCESS_ATTACH block missing")
    body = attach.group("body")
    for token in ("xrRender_test_hw(", "xr_vk_bootstrap_", "LoadLibrary(", "LoadLibraryA(", "LoadLibraryW(", "FreeLibrary("):
        if token in body:
            raise RuntimeError(f"Vulkan startup validation: loader-lock work remains in DllMain: {token}")
    for token in ("::Render = &RImplementation", "xrRender_initconsole()"):
        if token not in body:
            raise RuntimeError(f"Vulkan startup validation: renderer ABI binding missing {token}")

    life = lifecycle.read_text(encoding="utf-8", errors="ignore")
    attach_call = "xr_vk_bootstrap_attach_window(Device.m_hWnd, Device.dwWidth, Device.dwHeight)"
    if attach_call not in life:
        raise RuntimeError("Vulkan startup validation: deferred HWND runtime attach missing")
    if "xr_vk_bootstrap_frame();" in life:
        raise RuntimeError("Vulkan startup validation: obsolete OnFrame present hook remains")

    vk = bootstrap.read_text(encoding="utf-8", errors="ignore")
    if "if (!window_handle || !xr_vk_bootstrap_initialize())" not in vk:
        raise RuntimeError("Vulkan startup validation: HWND attach is not the lazy initialization boundary")

    rr = render.read_text(encoding="utf-8", errors="ignore")
    if 'strstr(Core.Params, "-vkpresent")' in rr:
        raise RuntimeError("Vulkan startup validation: obsolete secondary -vkpresent switch remains")
    scope = rr.find("class xr_vk_render_frame_scope")
    ready = rr.find("xr_vk_bootstrap_runtime_ready()", scope)
    begin = rr.find("xr_vk_bootstrap_begin_frame()", ready)
    end = rr.find("xr_vk_bootstrap_end_frame()", begin)
    render_fn = rr.find("void CRender::Render()")
    scope_instance = rr.find("xr_vk_render_frame_scope vk_frame_scope;", render_fn)
    if min(scope, ready, begin, end, render_fn, scope_instance) < 0:
        raise RuntimeError("Vulkan startup validation: Render-scoped frame lifecycle incomplete")
    if not scope < ready < begin < end or not render_fn < scope_instance:
        raise RuntimeError("Vulkan startup validation: Render-scoped startup/present order invalid")

    print("[validate-vulkan-startup] -vulkan selection + R2/R1 fallback + loader-lock-safe HWND init + automatic Render-scoped present verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the complete XR_3DA -> xrRender_VK startup and present path.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
