from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    paths = {
        "header": root / "xr_3da" / "R_Backend.h",
        "runtime": root / "xr_3da" / "R_Backend_Runtime.h",
        "api": root / "xr_3da" / "EngineAPI.cpp",
        "vk": root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    header = paths["header"].read_text(encoding="utf-8")
    runtime = paths["runtime"].read_text(encoding="utf-8")
    api = paths["api"].read_text(encoding="utf-8")
    vk = paths["vk"].read_text(encoding="utf-8")

    for token in (
        "xr_vk_backend_draw_indexed_fn",
        "xr_vk_backend_draw_fn",
        "IDirect3DVertexShader9* vertex_shader",
        "IDirect3DPixelShader9* pixel_shader",
        "LPCSTR vertex_shader_name",
        "LPCSTR pixel_shader_name",
        "g_xr_vk_backend_draw_indexed",
        "g_xr_vk_backend_draw",
    ):
        if token not in header:
            raise RuntimeError(f"backend dispatch validation: missing contract token {token}")

    indexed_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, baseV, startV, countV, startI, PC)"
    plain_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, startV, PC)"
    indexed_dispatch = runtime.find(indexed_call)
    indexed_fallback = runtime.find("HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC)")
    plain_dispatch = runtime.find(plain_call)
    plain_fallback = runtime.find("HW.pDevice->DrawPrimitive(T, startV, PC)")
    if min(indexed_dispatch, indexed_fallback, plain_dispatch, plain_fallback) < 0:
        raise RuntimeError("backend dispatch validation: handle+name production Render dispatch/fallback path incomplete")
    if indexed_dispatch > indexed_fallback or plain_dispatch > plain_fallback:
        raise RuntimeError("backend dispatch validation: D3D fallback executes before Vulkan dispatch")

    for symbol in ("xrRender_vk_backend_draw_indexed", "xrRender_vk_backend_draw"):
        if f'GetProcAddress(hRender, "{symbol}")' not in api:
            raise RuntimeError(f"backend dispatch validation: EngineAPI does not resolve {symbol}")
        if f"__cdecl {symbol}" not in vk:
            raise RuntimeError(f"backend dispatch validation: renderer does not export {symbol}")

    export_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    if export_start < 0:
        raise RuntimeError("backend dispatch validation: indexed renderer export missing")
    export_slice = vk[export_start:]
    for token in (
        "IDirect3DVertexShader9* vertex_shader",
        "IDirect3DPixelShader9* pixel_shader",
        "LPCSTR vertex_shader_name",
        "LPCSTR pixel_shader_name",
        "!vertex_shader || !pixel_shader",
        "!vertex_shader_name || !pixel_shader_name",
        "return FALSE;",
    ):
        if token not in export_slice:
            raise RuntimeError(f"backend dispatch validation: renderer export missing {token}")

    stale_calls = (
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV",
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV",
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV",
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV",
    )
    for token in stale_calls:
        if token in runtime:
            raise RuntimeError(f"backend dispatch validation: stale incomplete dispatch remains: {token}")

    if "vk_vs_name = _n;" not in runtime or "vk_ps_name = _n;" not in runtime:
        raise RuntimeError("backend dispatch validation: release-safe shader names are not captured")

    if "D3DPT_TRIANGLELIST" in runtime[runtime.find("ICF void CBackend::Render"):runtime.find("ICF void CBackend::set_Shader")]:
        raise RuntimeError("backend dispatch validation: production draw path hard-codes triangle-list topology")

    print("[vulkan-backend-dispatch] VS/PS handles + stable names + indexed/non-indexed renderer ABI + D3D fallback verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live SHOC CBackend to Vulkan renderer dispatch with shader handles and stable names.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
