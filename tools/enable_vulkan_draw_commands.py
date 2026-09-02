from __future__ import annotations

import argparse
from pathlib import Path


def install_draw_commands(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    header = renderer / "vk_bootstrap.h"
    if not source.is_file() or not header.is_file():
        raise FileNotFoundError("Vulkan draw-command layer requires materialized dynamic-state frame path")

    text = source.read_text(encoding="utf-8")

    fn_marker = "    PFN_vkCmdSetScissor g_vkCmdSetScissor = NULL;\n"
    fn_block = fn_marker + '''    PFN_vkCmdBindPipeline g_vkCmdBindPipeline = NULL;
    PFN_vkCmdBindVertexBuffers g_vkCmdBindVertexBuffers = NULL;
    PFN_vkCmdBindIndexBuffer g_vkCmdBindIndexBuffer = NULL;
    PFN_vkCmdDraw g_vkCmdDraw = NULL;
    PFN_vkCmdDrawIndexed g_vkCmdDrawIndexed = NULL;
'''
    if "PFN_vkCmdBindPipeline g_vkCmdBindPipeline" not in text:
        if fn_marker not in text:
            raise RuntimeError("Vulkan draw commands: function-table marker not found")
        text = text.replace(fn_marker, fn_block, 1)

    clear_marker = "        g_vkCmdSetScissor = NULL;\n"
    clear_block = clear_marker + '''        g_vkCmdBindPipeline = NULL;
        g_vkCmdBindVertexBuffers = NULL;
        g_vkCmdBindIndexBuffer = NULL;
        g_vkCmdDraw = NULL;
        g_vkCmdDrawIndexed = NULL;
'''
    if "        g_vkCmdBindPipeline = NULL;\n" not in text:
        if clear_marker not in text:
            raise RuntimeError("Vulkan draw commands: clear-table marker not found")
        text = text.replace(clear_marker, clear_block, 1)

    load_marker = "        XR_VK_LOAD_DEVICE(vkCmdSetScissor);\n"
    load_block = load_marker + '''        XR_VK_LOAD_DEVICE(vkCmdBindPipeline);
        XR_VK_LOAD_DEVICE(vkCmdBindVertexBuffers);
        XR_VK_LOAD_DEVICE(vkCmdBindIndexBuffer);
        XR_VK_LOAD_DEVICE(vkCmdDraw);
        XR_VK_LOAD_DEVICE(vkCmdDrawIndexed);
'''
    if "XR_VK_LOAD_DEVICE(vkCmdBindPipeline)" not in text:
        if load_marker not in text:
            raise RuntimeError("Vulkan draw commands: device-load marker not found")
        text = text.replace(load_marker, load_block, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "PFN_vkCmdBindPipeline g_vkCmdBindPipeline",
        "PFN_vkCmdBindVertexBuffers g_vkCmdBindVertexBuffers",
        "PFN_vkCmdBindIndexBuffer g_vkCmdBindIndexBuffer",
        "PFN_vkCmdDraw g_vkCmdDraw",
        "PFN_vkCmdDrawIndexed g_vkCmdDrawIndexed",
        "XR_VK_LOAD_DEVICE(vkCmdBindPipeline)",
        "XR_VK_LOAD_DEVICE(vkCmdBindVertexBuffers)",
        "XR_VK_LOAD_DEVICE(vkCmdBindIndexBuffer)",
        "XR_VK_LOAD_DEVICE(vkCmdDraw)",
        "XR_VK_LOAD_DEVICE(vkCmdDrawIndexed)",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan draw-command validation failed: missing {token}")

    print("[vulkan-draw] graphics pipeline, vertex/index binding and draw commands loaded for the next geometry bridge")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install native Vulkan draw command entry points for RC6 xrRender_VK.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_draw_commands(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
