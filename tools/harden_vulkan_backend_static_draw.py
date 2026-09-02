from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")
    indexed_export = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed'
    plain_export = 'extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw('
    indexed_start = text.find(indexed_export)
    plain_start = text.find(plain_export, indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan static backend draw: backend exports not found")

    indexed = text[indexed_start:plain_start]
    static_indexed = r'''

    if (xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, index_buffer, vertex_stride, base_vertex, start_vertex,
            vertex_count, start_index, primitive_count))
        return TRUE;'''
    if "xr_vk_record_static_indexed_backend_draw(command_buffer" not in indexed:
        fallback = indexed.rfind("    return FALSE;")
        if fallback < 0:
            raise RuntimeError("Vulkan static backend draw: indexed final fallback not found")
        indexed = indexed[:fallback] + static_indexed + "\n" + indexed[fallback:]
        text = text[:indexed_start] + indexed + text[plain_start:]

    plain_start = text.find(plain_export, indexed_start)
    plain = text[plain_start:]
    static_plain = r'''

    if (xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive,
            vertex_buffer, vertex_stride, start_vertex, primitive_count))
        return TRUE;'''
    if "xr_vk_record_static_backend_draw(command_buffer" not in plain:
        fallback = plain.rfind("    return FALSE;")
        if fallback < 0:
            raise RuntimeError("Vulkan static backend draw: plain final fallback not found")
        plain = plain[:fallback] + static_plain + "\n" + plain[fallback:]
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_record_static_indexed_backend_draw(command_buffer, pipeline, primitive",
        "xr_vk_record_static_backend_draw(command_buffer, pipeline, primitive",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan static backend draw validation failed: missing {token}")
    print("[vulkan-backend-static-draw] mirrored level/model VB/IB draws now record on Vulkan before D3D9 fallback")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute mirrored SHOC static level/model backend draws on Vulkan.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
