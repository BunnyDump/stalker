from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    indexed_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if indexed_start < 0 or plain_start < 0:
        raise RuntimeError("Vulkan backend active-frame hardening: renderer exports not found")

    indexed = text[indexed_start:plain_start]
    if "xr_vk_bootstrap_active_command_buffer()" not in indexed:
        guard_end = indexed.find("        return FALSE;")
        if guard_end < 0:
            raise RuntimeError("Vulkan backend active-frame hardening: indexed fail-closed guard not found")
        guard_end += len("        return FALSE;")
        active_guard = r'''

    VkCommandBuffer command_buffer = reinterpret_cast<VkCommandBuffer>(xr_vk_bootstrap_active_command_buffer());
    if (command_buffer == VK_NULL_HANDLE)
        return FALSE;'''
        indexed = indexed[:guard_end] + active_guard + indexed[guard_end:]
        text = text[:indexed_start] + indexed + text[plain_start:]

    # Re-resolve the second export because the first insertion changed offsets.
    plain_start = text.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    if plain_start < 0:
        raise RuntimeError("Vulkan backend active-frame hardening: plain export disappeared")
    plain = text[plain_start:]
    if "xr_vk_bootstrap_active_command_buffer()" not in plain:
        guard_end = plain.find("        return FALSE;")
        if guard_end < 0:
            raise RuntimeError("Vulkan backend active-frame hardening: plain fail-closed guard not found")
        guard_end += len("        return FALSE;")
        active_guard = r'''

    VkCommandBuffer command_buffer = reinterpret_cast<VkCommandBuffer>(xr_vk_bootstrap_active_command_buffer());
    if (command_buffer == VK_NULL_HANDLE)
        return FALSE;'''
        plain = plain[:guard_end] + active_guard + plain[guard_end:]
        text = text[:plain_start] + plain

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    indexed_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw_indexed')
    plain_start = final.find('extern "C" __declspec(dllexport) BOOL __cdecl xrRender_vk_backend_draw(', indexed_start)
    indexed = final[indexed_start:plain_start]
    plain = final[plain_start:]

    required = (
        "VkCommandBuffer command_buffer = reinterpret_cast<VkCommandBuffer>(xr_vk_bootstrap_active_command_buffer());",
        "if (command_buffer == VK_NULL_HANDLE)",
    )
    for label, block in (("indexed", indexed), ("plain", plain)):
        for token in required:
            if token not in block:
                raise RuntimeError(f"Vulkan backend active-frame validation failed in {label} export: missing {token}")
        runtime_guard = block.find("xr_vk_bootstrap_runtime_ready()")
        command_guard = block.find("xr_vk_bootstrap_active_command_buffer()")
        final_fallback = block.rfind("return FALSE;")
        if min(runtime_guard, command_guard, final_fallback) < 0 or not runtime_guard < command_guard < final_fallback:
            raise RuntimeError(f"Vulkan backend active-frame validation failed in {label} export: guard order invalid")

    print("[vulkan-backend-active-frame] backend Vulkan draws require the live R2 render-pass command buffer")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject Vulkan backend draw dispatch outside the active R2 frame command buffer.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
