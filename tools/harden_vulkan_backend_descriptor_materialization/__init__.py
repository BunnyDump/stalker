from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_impl():
    impl_path = Path(__file__).resolve().parent.parent / "harden_vulkan_backend_descriptor_materialization.py"
    spec = importlib.util.spec_from_file_location("_xr_vk_backend_descriptor_materialization_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Vulkan descriptor materialization implementation: {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def harden(root: Path) -> None:
    root = Path(root).resolve()
    source = root / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    # The preceding dynamic-draw hardener deliberately feeds VK_NULL_HANDLE while the
    # production resource gate is closed. Normalize that precursor to the marker consumed
    # by the descriptor materializer; the implementation immediately replaces it with the
    # real per-draw descriptor_set argument before validation/compilation.
    text = source.read_text(encoding="utf-8")
    fail_closed = "xr_vk_make_indexed_draw_packet(pipeline, VK_NULL_HANDLE, D3DFMT_INDEX16, primitive, start_index,"
    precursor = "xr_vk_make_indexed_draw_packet(pipeline, D3DFMT_INDEX16, primitive, start_index,"
    live = "xr_vk_make_indexed_draw_packet(pipeline, descriptor_set, D3DFMT_INDEX16, primitive, start_index,"
    if live not in text and fail_closed in text:
        source.write_text(text.replace(fail_closed, precursor, 1), encoding="utf-8")

    impl = _load_impl()
    impl.harden(root)
