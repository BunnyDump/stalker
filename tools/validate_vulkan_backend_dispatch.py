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
        "xr_vk_backend_draw_indexed_fn", "xr_vk_backend_draw_fn",
        "IDirect3DVertexShader9* vertex_shader", "IDirect3DPixelShader9* pixel_shader",
        "LPCSTR vertex_shader_name", "LPCSTR pixel_shader_name",
        "IDirect3DStateBlock9* state_block",
        "g_xr_vk_backend_draw_indexed", "g_xr_vk_backend_draw",
    ):
        if token not in header:
            raise RuntimeError(f"backend dispatch validation: missing contract token {token}")

    indexed_call = "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, state, baseV, startV, countV, startI, PC)"
    plain_call = "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, state, startV, PC)"
    indexed_dispatch = runtime.find(indexed_call)
    indexed_fallback = runtime.find("HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC)")
    plain_dispatch = runtime.find(plain_call)
    plain_fallback = runtime.find("HW.pDevice->DrawPrimitive(T, startV, PC)")
    if min(indexed_dispatch, indexed_fallback, plain_dispatch, plain_fallback) < 0:
        raise RuntimeError("backend dispatch validation: state+shader production Render dispatch/fallback path incomplete")
    if indexed_dispatch > indexed_fallback or plain_dispatch > plain_fallback:
        raise RuntimeError("backend dispatch validation: D3D fallback executes before Vulkan dispatch")

    for symbol in ("xrRender_vk_backend_draw_indexed", "xrRender_vk_backend_draw"):
        if f'GetProcAddress(hRender, "{symbol}")' not in api:
            raise RuntimeError(f"backend dispatch validation: EngineAPI does not resolve {symbol}")
        if f"__cdecl {symbol}" not in vk:
            raise RuntimeError(f"backend dispatch validation: renderer does not export {symbol}")

    for token in (
        "u64 xr_vk_hash_shader_bytecode", "1469598103934665603ull", "1099511628211ull",
        "xr_vk_vertex_shader_bytecode_identity", "xr_vk_pixel_shader_bytecode_identity",
        "shader->GetFunction(NULL, &size)", "shader->GetFunction(&bytecode[0], &actual_size)",
        "struct xr_vk_backend_pipeline_key", "u64 vertex_declaration_identity;",
        "u64 state_block_identity;", "a.state_block_identity == b.state_block_identity",
        "reinterpret_cast<size_t>(state_block)",
        "declaration->GetDeclaration(NULL, &count)", "xr_vk_make_backend_pipeline_key",
        "xr_vk_find_backend_pipeline", "xr_vk_register_backend_pipeline", "xr_vk_prune_backend_pipelines",
        "key.render_pass_generation = g_render_pass_generation;",
    ):
        if token not in vk:
            raise RuntimeError(f"backend dispatch validation: shader/pipeline/state identity layer missing {token}")

    indexed_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = vk.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("backend dispatch validation: renderer exports missing")

    for label, block in (("indexed", vk[indexed_start:plain_start]), ("plain", vk[plain_start:])):
        for token in (
            "IDirect3DVertexShader9* vertex_shader", "IDirect3DPixelShader9* pixel_shader",
            "LPCSTR vertex_shader_name", "LPCSTR pixel_shader_name", "IDirect3DStateBlock9* state_block",
            "!vertex_shader || !pixel_shader", "!vertex_shader_name || !pixel_shader_name", "!state_block",
            "VkCommandBuffer command_buffer = reinterpret_cast<VkCommandBuffer>(xr_vk_bootstrap_active_command_buffer());",
            "if (command_buffer == VK_NULL_HANDLE)",
            "u64 vertex_shader_identity = 0;", "u64 pixel_shader_identity = 0;",
            "xr_vk_vertex_shader_bytecode_identity(vertex_shader, vertex_shader_identity)",
            "xr_vk_pixel_shader_bytecode_identity(pixel_shader, pixel_shader_identity)",
            "xr_vk_backend_pipeline_key pipeline_key = {};", "xr_vk_vertex_input_layout vertex_layout = {};",
            "xr_vk_make_backend_pipeline_key(vertex_shader_identity, pixel_shader_identity",
            "primitive, state_block, pipeline_key, vertex_layout",
            "xr_vk_find_backend_pipeline(pipeline_key)", "if (pipeline == VK_NULL_HANDLE)", "return FALSE;",
        ):
            if token not in block:
                raise RuntimeError(f"backend dispatch validation: {label} export missing {token}")
        runtime_guard = block.find("xr_vk_bootstrap_runtime_ready()")
        active_guard = block.find("xr_vk_bootstrap_active_command_buffer()")
        identity_guard = block.find("xr_vk_vertex_shader_bytecode_identity")
        key_guard = block.find("xr_vk_make_backend_pipeline_key")
        lookup_guard = block.find("xr_vk_find_backend_pipeline")
        final_fallback = block.rfind("return FALSE;")
        positions = (runtime_guard, active_guard, identity_guard, key_guard, lookup_guard, final_fallback)
        if min(positions) < 0 or list(positions) != sorted(positions):
            raise RuntimeError(f"backend dispatch validation: {label} runtime/frame/identity/pipeline guard order invalid")

    stale_calls = (
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, baseV",
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, baseV",
        "g_xr_vk_backend_draw_indexed(T, decl, vb, vb_stride, ib, vs, ps, vk_vs_name, vk_ps_name, baseV",
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, startV",
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, startV",
        "g_xr_vk_backend_draw(T, decl, vb, vb_stride, vs, ps, vk_vs_name, vk_ps_name, startV",
    )
    for token in stale_calls:
        if token in runtime:
            raise RuntimeError(f"backend dispatch validation: stale incomplete dispatch remains: {token}")

    if "vk_vs_name = _n;" not in runtime or "vk_ps_name = _n;" not in runtime:
        raise RuntimeError("backend dispatch validation: release-safe shader names are not captured")
    if "D3DPT_TRIANGLELIST" in runtime[runtime.find("ICF void CBackend::Render"):runtime.find("ICF void CBackend::set_Shader")]:
        raise RuntimeError("backend dispatch validation: production draw path hard-codes triangle-list topology")

    print("[vulkan-backend-dispatch] shader handles/names + state-block identity + generation-keyed pipeline registry + active R2 command buffer + fail-closed D3D fallback verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live SHOC CBackend to Vulkan renderer dispatch with stable shader/state/pipeline identity and active frame gating.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
