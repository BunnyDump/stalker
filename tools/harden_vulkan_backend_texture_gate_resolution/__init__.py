from __future__ import annotations

import importlib.util
from pathlib import Path

from harden_vulkan_backend_descriptor_materialization import harden as harden_descriptor_materialization


def _load_legacy_module():
    legacy_path = Path(__file__).resolve().parent.parent / "harden_vulkan_backend_texture_gate_resolution.py"
    spec = importlib.util.spec_from_file_location("_xr_vk_texture_gate_resolution_legacy", legacy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load legacy Vulkan texture-gate hardener: {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def harden(root: Path) -> None:
    legacy = _load_legacy_module()
    legacy.harden(root)
    harden_descriptor_materialization(root)
