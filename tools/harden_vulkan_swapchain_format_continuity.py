from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkFormat g_swapchain_format = VK_FORMAT_UNDEFINED;\n"
    preferred_state = state_marker + "    VkFormat g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;\n"
    if "g_swapchain_preferred_format" not in text:
        if state_marker not in text:
            raise RuntimeError("Swapchain format continuity: format state marker not found")
        text = text.replace(state_marker, preferred_state, 1)

    old_selection = r'''        VkSurfaceFormatKHR chosen_format = formats[0];
        if (format_count == 1 && formats[0].format == VK_FORMAT_UNDEFINED)
        {
            chosen_format.format = VK_FORMAT_B8G8R8A8_UNORM;
            chosen_format.colorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
        }
        else
        {
            for (unsigned i = 0; i < format_count; ++i)
            {
                if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM && formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                {
                    chosen_format = formats[i];
                    break;
                }
            }
        }
'''
    new_selection = r'''        VkSurfaceFormatKHR chosen_format = formats[0];
        bool preferred_format_found = g_swapchain_preferred_format == VK_FORMAT_UNDEFINED;
        if (format_count == 1 && formats[0].format == VK_FORMAT_UNDEFINED)
        {
            chosen_format.format = g_swapchain_preferred_format != VK_FORMAT_UNDEFINED ?
                g_swapchain_preferred_format : VK_FORMAT_B8G8R8A8_UNORM;
            chosen_format.colorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR;
            preferred_format_found = true;
        }
        else
        {
            if (g_swapchain_preferred_format != VK_FORMAT_UNDEFINED)
            {
                for (unsigned i = 0; i < format_count; ++i)
                {
                    if (formats[i].format == g_swapchain_preferred_format)
                    {
                        chosen_format = formats[i];
                        preferred_format_found = true;
                        break;
                    }
                }
            }
            else
            {
                for (unsigned i = 0; i < format_count; ++i)
                {
                    if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM && formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                    {
                        chosen_format = formats[i];
                        break;
                    }
                }
            }
        }
        if (!preferred_format_found)
            return false;
'''
    if "bool preferred_format_found" not in text:
        if old_selection not in text:
            raise RuntimeError("Swapchain format continuity: selection block changed")
        text = text.replace(old_selection, new_selection, 1)

    tx_start = text.find("bool xr_vk_transactional_recreate_swapchain(unsigned width, unsigned height)")
    tx_end = text.find("bool xr_vk_bootstrap_resize(unsigned width, unsigned height)", tx_start)
    if tx_start < 0 or tx_end < 0:
        raise RuntimeError("Swapchain format continuity: transaction helper not found")
    tx = text[tx_start:tx_end]

    capture_marker = "    const xr_vk_swapchain_state old_state = xr_vk_capture_swapchain_state();\n"
    capture_replacement = capture_marker + "    g_swapchain_preferred_format = old_state.format;\n"
    if "g_swapchain_preferred_format = old_state.format;" not in tx:
        if capture_marker not in tx:
            raise RuntimeError("Swapchain format continuity: old state capture marker not found")
        tx = tx.replace(capture_marker, capture_replacement, 1)

    # Clear the temporary preference on every transaction exit. Creation has already
    # selected the actual format before these points.
    tx = tx.replace(
        "            return false;\n        }\n        return true;\n    }\n\n    const xr_vk_swapchain_state new_state",
        "            g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;\n            return false;\n        }\n        g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;\n        return true;\n    }\n\n    const xr_vk_swapchain_state new_state",
        1,
    )
    success_marker = "    xr_vk_restore_swapchain_state(new_state);\n    return true;\n"
    success_replacement = "    xr_vk_restore_swapchain_state(new_state);\n    g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;\n    return true;\n"
    if success_replacement not in tx:
        if success_marker not in tx:
            raise RuntimeError("Swapchain format continuity: success exit marker not found")
        tx = tx.replace(success_marker, success_replacement, 1)

    text = text[:tx_start] + tx + text[tx_end:]
    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "VkFormat g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;",
        "bool preferred_format_found",
        "formats[i].format == g_swapchain_preferred_format",
        "if (!preferred_format_found)",
        "g_swapchain_preferred_format = old_state.format;",
        "g_swapchain_preferred_format = VK_FORMAT_UNDEFINED;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Swapchain format continuity validation failed: missing {token}")

    transaction = final[final.index("bool xr_vk_transactional_recreate_swapchain"):final.index("bool xr_vk_bootstrap_resize")]
    set_pref = transaction.index("g_swapchain_preferred_format = old_state.format;")
    handoff = transaction.index("xr_vk_create_swapchain(width, height, old_state.swapchain)")
    if not set_pref < handoff:
        raise RuntimeError("Swapchain format continuity validation failed: preference set after recreation")

    print("[vulkan-swapchain-format] surface format continuity enforced across pipeline-preserving recreation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preserve Vulkan swapchain format while graphics pipelines survive resize.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
