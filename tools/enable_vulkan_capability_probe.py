from __future__ import annotations

import argparse
from pathlib import Path

PROBE_SOURCE = r'''#include "stdafx.h"
#include "vk_bootstrap.h"

BOOL xrRender_test_hw()
{
    if (!xr_vk_bootstrap_initialize())
        return FALSE;

    const unsigned physical_device_count = xr_vk_bootstrap_physical_device_count();
    xr_vk_bootstrap_shutdown();

    return physical_device_count > 0 ? TRUE : FALSE;
}
'''


def enable_vulkan_capability_probe(root: Path) -> None:
    root = root.resolve()
    renderer = root / "xr_3da" / "xrRender_VK"
    if not renderer.is_dir():
        raise FileNotFoundError(renderer)

    bootstrap_header = renderer / "vk_bootstrap.h"
    if not bootstrap_header.is_file():
        raise RuntimeError("Vulkan capability probe requires vk_bootstrap.h; run enable_vulkan_bootstrap.py first")

    source = renderer / "r2_test_hw.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    source.write_text(PROBE_SOURCE, encoding="utf-8")

    text = source.read_text(encoding="utf-8")
    required = (
        "xr_vk_bootstrap_initialize()",
        "xr_vk_bootstrap_physical_device_count()",
        "xr_vk_bootstrap_shutdown()",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan capability probe validation: missing {token}")

    forbidden = ("D3DCAPS9", "GetDeviceCaps", "PixelShaderVersion", "NumSimultaneousRTs")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"Vulkan capability probe validation: legacy D3D9 token remains: {token}")

    print("[vulkan-capability] xrRender_test_hw now probes Vulkan loader/instance/physical devices instead of D3D9 caps")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace xrRender_VK D3D9 hardware probe with a native Vulkan capability probe.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    enable_vulkan_capability_probe(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
