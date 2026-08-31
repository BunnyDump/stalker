from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_impl():
    impl_path = Path(__file__).resolve().parent.parent / "enable_vulkan_material_descriptors.py"
    spec = importlib.util.spec_from_file_location("_xr_vk_material_descriptors_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load material descriptor installer: {impl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_material_descriptors(root: Path) -> None:
    impl = _load_impl()
    impl.install_material_descriptors(Path(root))

    source = Path(root).resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    final = source.read_text(encoding="utf-8")
    required = (
        "VkPipeline pipeline, VkDescriptorSet descriptor_set",
        "D3DFORMAT index_format, D3DPRIMITIVETYPE primitive_type",
        "draw.primitive_type = primitive_type;",
        "draw.descriptor_set = descriptor_set;",
        "pipeline == VK_NULL_HANDLE || descriptor_set == VK_NULL_HANDLE",
        "xr_vk_bind_material_descriptor(command_buffer, draw.descriptor_set)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Topology-aware material descriptor validation failed: missing {token}")

    print("[vulkan-materials-v2] delegated topology-aware descriptor installer validated")
