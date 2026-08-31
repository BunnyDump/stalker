from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    root = root.resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    loader = root / "xr_3da" / "xrRender_VK" / "r2_loader.cpp"
    visual = root / "xr_3da" / "xrRender" / "FVisual.cpp"
    backend = root / "xr_3da" / "R_Backend_Runtime.h"
    for path in (source, loader, visual, backend):
        if not path.is_file():
            raise FileNotFoundError(path)

    text = source.read_text(encoding="utf-8")
    load_text = loader.read_text(encoding="utf-8")
    visual_text = visual.read_text(encoding="utf-8")
    backend_text = backend.read_text(encoding="utf-8")

    required_source = (
        "struct xr_vk_static_geometry_mirror",
        "xrRender_vk_register_static_vertex_buffer",
        "xrRender_vk_register_static_index_buffer",
        "xrRender_vk_clear_static_geometry",
        "xr_vk_record_static_indexed_backend_draw",
        "xr_vk_record_static_backend_draw",
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive",
        "g_vkCmdDrawIndexed(command_buffer, index_count, 1, 0, static_cast<s32>(base_vertex), 0)",
        "g_vkCmdDraw(command_buffer, vertex_count, 1, start_vertex, 0)",
    )
    for token in required_source:
        if token not in text:
            raise RuntimeError(f"Vulkan static backend draw validation failed: source missing {token}")

    for token in (
        'GetModuleHandleA("xrRender_VK.dll")',
        'GetProcAddress(module, "xrRender_vk_register_static_vertex_buffer")',
        'GetProcAddress(module, "xrRender_vk_register_static_index_buffer")',
        "xr_vk_try_register_static_vb(p_rm_Vertices, bytes, vCount * vStride);",
        "xr_vk_try_register_static_ib(p_rm_Indices, bytes, iCount * 2, D3DFMT_INDEX16);",
    ):
        if token not in visual_text:
            raise RuntimeError(f"Vulkan static backend draw validation failed: FVisual missing {token}")

    for token in (
        "xr_vk_register_level_vb(_VB[i], pData, vCount * vSize);",
        "xr_vk_register_level_ib(_IB[i], pData, iCount * 2);",
        "xr_vk_clear_level_geometry();",
    ):
        if token not in load_text:
            raise RuntimeError(f"Vulkan static backend draw validation failed: r2_loader missing {token}")

    # Ensure registration happens while the source bytes are still locked and valid.
    vb_reg = load_text.find("xr_vk_register_level_vb(_VB[i], pData, vCount * vSize);")
    vb_unlock = load_text.find("_VB[i]->Unlock();", vb_reg)
    ib_reg = load_text.find("xr_vk_register_level_ib(_IB[i], pData, iCount * 2);")
    ib_unlock = load_text.find("_IB[i]->Unlock();", ib_reg)
    if min(vb_reg, vb_unlock, ib_reg, ib_unlock) < 0 or not vb_reg < vb_unlock or not ib_reg < ib_unlock:
        raise RuntimeError("Vulkan static backend draw validation failed: level registration must precede Unlock")

    indexed_export = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_export = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_export)
    indexed = text[indexed_export:plain_export]
    plain = text[plain_export:]
    indexed_call = indexed.find("xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive")
    indexed_true = indexed.find("return TRUE;", indexed_call)
    indexed_fallback = indexed.rfind("return FALSE;")
    plain_call = plain.find("xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive")
    plain_true = plain.find("return TRUE;", plain_call)
    plain_fallback = plain.rfind("return FALSE;")
    if min(indexed_call, indexed_true, indexed_fallback, plain_call, plain_true, plain_fallback) < 0:
        raise RuntimeError("Vulkan static backend draw validation failed: success/fallback markers missing")
    if not indexed_call < indexed_true < indexed_fallback or not plain_call < plain_true < plain_fallback:
        raise RuntimeError("Vulkan static backend draw validation failed: success/fallback order invalid")

    for token in (
        "HW.pDevice->DrawIndexedPrimitive(T, baseV, startV, countV, startI, PC)",
        "HW.pDevice->DrawPrimitive(T, startV, PC)",
    ):
        if token not in backend_text:
            raise RuntimeError(f"Vulkan static backend draw validation failed: D3D9 fallback removed: {token}")

    print("[vulkan-backend-static-draw] static level/OGF mirror registration + Vulkan recording + D3D9 fallback verified")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vulkan execution for mirrored static level/model geometry.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
