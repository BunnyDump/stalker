from __future__ import annotations

import argparse
import re
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    engine_api = root / "xr_3da" / "EngineAPI.cpp"
    renderer = root / "xr_3da" / "xrRender_VK"
    dll_entry = renderer / "xrRender_R2.cpp"
    test_hw = renderer / "r2_test_hw.cpp"
    lifecycle = renderer / "r2.cpp"
    render = renderer / "r2_R_render.cpp"
    bootstrap = renderer / "vk_bootstrap.cpp"
    for path in (engine_api, dll_entry, test_hw, lifecycle, render, bootstrap):
        if not path.is_file():
            raise FileNotFoundError(path)

    engine = engine_api.read_text(encoding="utf-8", errors="ignore")
    required_engine = (
        '"xrRender_VK.dll"',
        'strstr(Core.Params, "-vulkan")',
        "LoadLibrary(vk_name)",
        'GetProcAddress(hRender, "xrRender_vk_capability_probe")',
        'GetProcAddress(hRender, "xrRender_vk_activate")',
        "vk_probe()",
        "vk_activate()",
        "FreeLibrary(hRender)",
        "hRender = 0;",
    )
    for token in required_engine:
        if token not in engine:
            raise RuntimeError(f"Vulkan startup validation: engine handshake missing {token}")

    vk_select = engine.find('strstr(Core.Params, "-vulkan")')
    vk_load = engine.find("LoadLibrary(vk_name)", vk_select)
    probe_resolve = engine.find('GetProcAddress(hRender, "xrRender_vk_capability_probe")', vk_load)
    activate_resolve = engine.find('GetProcAddress(hRender, "xrRender_vk_activate")', probe_resolve)
    probe_call = engine.find("vk_probe()", activate_resolve)
    activate_call = engine.find("vk_activate()", probe_call)
    unload = engine.find("FreeLibrary(hRender)", activate_call)
    r2_load = engine.find("LoadLibrary(r2_name)", unload)
    r1_load = engine.find("LoadLibrary(r1_name)", r2_load)
    positions = (vk_select, vk_load, probe_resolve, activate_resolve, probe_call, activate_call, unload, r2_load, r1_load)
    if min(positions) < 0 or list(positions) != sorted(positions):
        raise RuntimeError("Vulkan startup validation: load -> probe -> activate -> unload/fallback order invalid")

    entry = dll_entry.read_text(encoding="utf-8", errors="ignore")
    attach = re.search(
        r"case\s+DLL_PROCESS_ATTACH\s*:\s*(?P<body>.*?)(?=\s*break\s*;)",
        entry,
        flags=re.DOTALL,
    )
    if not attach:
        raise RuntimeError("Vulkan startup validation: DLL_PROCESS_ATTACH block missing")
    body = attach.group("body")
    forbidden_attach = (
        "xrRender_test_hw",
        "xrRender_vk_capability_probe",
        "xrRender_vk_activate",
        "::Render = &RImplementation",
        "xrRender_initconsole",
        "xr_vk_bootstrap_",
        "LoadLibrary(",
        "LoadLibraryA(",
        "LoadLibraryW(",
        "FreeLibrary(",
    )
    for token in forbidden_attach:
        if token in body:
            raise RuntimeError(f"Vulkan startup validation: side effect remains under loader lock: {token}")

    activate = entry.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_activate()')
    bind = entry.find("::Render = &RImplementation", activate)
    console = entry.find("xrRender_initconsole()", bind)
    activation_return = entry.find("return TRUE;", console)
    if min(activate, bind, console, activation_return) < 0 or not activate < bind < console < activation_return:
        raise RuntimeError("Vulkan startup validation: explicit post-load activation export incomplete")

    probe_source = test_hw.read_text(encoding="utf-8", errors="ignore")
    probe_export = probe_source.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_capability_probe()')
    bootstrap_probe = probe_source.find("xr_vk_bootstrap_probe()", probe_export)
    legacy_wrapper = probe_source.find("BOOL xrRender_test_hw()", bootstrap_probe)
    if min(probe_export, bootstrap_probe, legacy_wrapper) < 0 or not probe_export < bootstrap_probe < legacy_wrapper:
        raise RuntimeError("Vulkan startup validation: exported capability probe/legacy wrapper incomplete")

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

    print("[validate-vulkan-startup] -vulkan load + post-load capability/activation handshake + safe unload/R2/R1 fallback + HWND init + automatic Render-scoped present verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate complete XR_3DA -> xrRender_VK capability-validated startup and present path.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
