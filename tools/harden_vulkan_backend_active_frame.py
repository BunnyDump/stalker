from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    render = renderer / "r2_R_render.cpp"
    for path in (source, render):
        if not path.is_file():
            raise FileNotFoundError(path)

    # xrRender_VK is selected explicitly by the engine. Once its Vulkan runtime is
    # ready, the real R2 Render() scope must own begin/end/present without requiring
    # a second hidden command-line switch.
    render_text = render.read_text(encoding="utf-8", errors="ignore")
    legacy_gate = 'xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent")'
    if legacy_gate in render_text:
        render_text = render_text.replace(legacy_gate, "xr_vk_bootstrap_runtime_ready()", 1)
        render.write_text(render_text, encoding="utf-8")
    render_text = render.read_text(encoding="utf-8", errors="ignore")
    if 'strstr(Core.Params, "-vkpresent")' in render_text:
        raise RuntimeError("Vulkan frame activation hardening: obsolete -vkpresent gate remains")
    scope = render_text.find("class xr_vk_render_frame_scope")
    begin = render_text.find("xr_vk_bootstrap_begin_frame()", scope)
    ready = render_text.rfind("xr_vk_bootstrap_runtime_ready()", scope, begin)
    end = render_text.find("xr_vk_bootstrap_end_frame()", begin)
    if min(scope, ready, begin, end) < 0 or not scope < ready < begin < end:
        raise RuntimeError("Vulkan frame activation hardening: runtime-ready RAII frame scope is incomplete")

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

    print("[vulkan-backend-active-frame] renderer-ready R2 frame presentation + live command-buffer draw gating installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate Vulkan presentation on renderer readiness and reject draws outside the active R2 frame.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
