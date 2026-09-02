from __future__ import annotations

import argparse
import re
from pathlib import Path


def _clear_failure_returns(block: str) -> str:
    return re.sub(
        r"(?m)^(\s*)return false;\s*$",
        r"\1{ xr_vk_clear_active_frame_state(); return false; }",
        block,
    )


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    header = renderer / "vk_bootstrap.h"
    source = renderer / "vk_bootstrap.cpp"
    lifecycle = renderer / "r2.cpp"
    render = renderer / "r2_R_render.cpp"
    for path in (header, source, lifecycle, render):
        if not path.is_file():
            raise FileNotFoundError(path)

    # Public frame lifecycle used by CRender::Render and the backend draw bridge.
    h = header.read_text(encoding="utf-8")
    old_decl = "bool xr_vk_bootstrap_frame();\n"
    new_decl = (
        "bool xr_vk_bootstrap_begin_frame();\n"
        "bool xr_vk_bootstrap_end_frame();\n"
        "bool xr_vk_bootstrap_frame();\n"
        "void* xr_vk_bootstrap_active_command_buffer();\n"
    )
    if "bool xr_vk_bootstrap_begin_frame();" not in h:
        if old_decl not in h:
            raise RuntimeError("Vulkan frame lifecycle: bootstrap frame declaration marker not found")
        h = h.replace(old_decl, new_decl, 1)
        header.write_text(h, encoding="utf-8")

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkFence g_frame_fence = VK_NULL_HANDLE;\n"
    state = state_marker + (
        "    bool g_frame_recording = false;\n"
        "    unsigned g_active_frame_image_index = ~0u;\n"
        "    VkResult g_active_frame_acquire_result = VK_SUCCESS;\n"
    )
    if "g_frame_recording" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan frame lifecycle: frame fence state marker not found")
        text = text.replace(state_marker, state, 1)

    # Materialize the monolithic, already-hardened frame into begin/end halves.
    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    runtime_ready = text.find("bool xr_vk_bootstrap_runtime_ready()", frame_start)
    if frame_start < 0 or runtime_ready < 0:
        raise RuntimeError("Vulkan frame lifecycle: monolithic frame function not found")
    frame = text[frame_start:runtime_ready]
    brace = frame.find("{")
    last_brace = frame.rfind("}")
    if brace < 0 or last_brace <= brace:
        raise RuntimeError("Vulkan frame lifecycle: frame body boundary not found")
    body = frame[brace + 1:last_brace]
    end_pass = body.find("g_vkCmdEndRenderPass(g_command_buffers[image_index])")
    if end_pass < 0:
        raise RuntimeError("Vulkan frame lifecycle: render-pass end marker not found")

    begin_body = body[:end_pass].rstrip()
    end_body = body[end_pass:].strip()
    if "g_vkCmdBeginRenderPass(g_command_buffers[image_index]" not in begin_body:
        raise RuntimeError("Vulkan frame lifecycle: render-pass begin marker not found")
    if "g_vkQueueSubmit" not in end_body or "g_vkQueuePresentKHR" not in end_body:
        raise RuntimeError("Vulkan frame lifecycle: submit/present tail not found")

    # end_frame owns an acquired image. Every failure must release the CPU-side
    # recording state so the next frame can safely retry/fall back to D3D9.
    end_body = _clear_failure_returns(end_body)
    end_body = end_body.replace(
        "presented == VK_SUBOPTIMAL_KHR || acquire == VK_SUBOPTIMAL_KHR",
        "presented == VK_SUBOPTIMAL_KHR || g_active_frame_acquire_result == VK_SUBOPTIMAL_KHR",
        1,
    )
    success = end_body.rfind("return true;")
    if success < 0:
        raise RuntimeError("Vulkan frame lifecycle: successful frame return not found")
    end_body = (
        end_body[:success]
        + "xr_vk_clear_active_frame_state();\n    return true;"
        + end_body[success + len("return true;"):]
    )

    split = r'''bool xr_vk_bootstrap_begin_frame()
{
    if (g_frame_recording)
        return false;
''' + begin_body.replace("\n    if (!xr_vk_bootstrap_runtime_ready())\n        return false;", "", 1) + r'''

    g_active_frame_image_index = image_index;
    g_active_frame_acquire_result = acquire;
    g_frame_recording = true;
    return true;
}

namespace
{
    void xr_vk_clear_active_frame_state()
    {
        g_frame_recording = false;
        g_active_frame_image_index = ~0u;
        g_active_frame_acquire_result = VK_SUCCESS;
    }
}

bool xr_vk_bootstrap_end_frame()
{
    if (!g_frame_recording || g_active_frame_image_index >= g_command_buffers.size())
        return false;
    const unsigned image_index = g_active_frame_image_index;

''' + end_body + r'''
}

bool xr_vk_bootstrap_frame()
{
    if (!xr_vk_bootstrap_begin_frame())
        return false;
    return xr_vk_bootstrap_end_frame();
}

void* xr_vk_bootstrap_active_command_buffer()
{
    if (!g_frame_recording || g_active_frame_image_index >= g_command_buffers.size())
        return NULL;
    return reinterpret_cast<void*>(g_command_buffers[g_active_frame_image_index]);
}

'''

    # The helper is used by end_frame before its textual definition in the split block.
    split = split.replace(
        "bool xr_vk_bootstrap_begin_frame()",
        "namespace { void xr_vk_clear_active_frame_state(); }\n\nbool xr_vk_bootstrap_begin_frame()",
        1,
    )
    text = text[:frame_start] + split + text[runtime_ready:]

    # Full teardown/reset must never preserve an active command buffer identity.
    destroy_start = text.find("void xr_vk_destroy_frame_resources()")
    destroy_end = text.find("void xr_vk_destroy_window_runtime()", destroy_start)
    if destroy_start < 0 or destroy_end < 0:
        raise RuntimeError("Vulkan frame lifecycle: frame-resource teardown not found")
    destroy = text[destroy_start:destroy_end]
    reset_marker = "        g_frame_fence = VK_NULL_HANDLE;\n"
    if "g_frame_recording = false;" not in destroy:
        if reset_marker not in destroy:
            raise RuntimeError("Vulkan frame lifecycle: teardown fence marker not found")
        destroy = destroy.replace(
            reset_marker,
            reset_marker + "        g_frame_recording = false;\n        g_active_frame_image_index = ~0u;\n"
            "        g_active_frame_acquire_result = VK_SUCCESS;\n",
            1,
        )
        text = text[:destroy_start] + destroy + text[destroy_end:]

    source.write_text(text, encoding="utf-8")

    # Remove the old presentation-only frame from OnFrame. OnFrame is bookkeeping,
    # not the actual R2 render interval.
    life = lifecycle.read_text(encoding="utf-8")
    old_hook = '\tif (xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent"))\n\t\txr_vk_bootstrap_frame();\n\n'
    if old_hook in life:
        life = life.replace(old_hook, "", 1)
    elif "xr_vk_bootstrap_frame();" in life:
        raise RuntimeError("Vulkan frame lifecycle: unexpected legacy OnFrame hook shape")
    lifecycle.write_text(life, encoding="utf-8")

    # Keep the render pass alive for the complete real R2 Render() call. RAII guarantees
    # end_frame on the menu and no-level early-return paths as well.
    r = render.read_text(encoding="utf-8")
    include_marker = '#include "..\\xr_object.h"\n'
    include = include_marker + '#include "vk_bootstrap.h"\n'
    if '#include "vk_bootstrap.h"' not in r:
        if include_marker not in r:
            raise RuntimeError("Vulkan frame lifecycle: r2_R_render include marker not found")
        r = r.replace(include_marker, include, 1)

    scope_marker = "IC bool pred_sp_sort(ISpatial* _1, ISpatial* _2)\n"
    scope = r'''namespace
{
    class xr_vk_render_frame_scope
    {
        bool active_;
    public:
        xr_vk_render_frame_scope() : active_(false)
        {
            if (xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent"))
                active_ = xr_vk_bootstrap_begin_frame();
        }
        ~xr_vk_render_frame_scope()
        {
            if (active_ && !xr_vk_bootstrap_end_frame())
                OutputDebugStringA("[X-Ray Vulkan] Failed to close/present R2 Vulkan frame. D3D fallback remains active.\n");
        }
    };
}

'''
    if "class xr_vk_render_frame_scope" not in r:
        if scope_marker not in r:
            raise RuntimeError("Vulkan frame lifecycle: R2 render scope marker not found")
        r = r.replace(scope_marker, scope + scope_marker, 1)

    render_marker = "void CRender::Render()\n{\n"
    render_open = render_marker + "\txr_vk_render_frame_scope vk_frame_scope;\n"
    if "xr_vk_render_frame_scope vk_frame_scope;" not in r:
        if render_marker not in r:
            raise RuntimeError("Vulkan frame lifecycle: CRender::Render marker not found")
        r = r.replace(render_marker, render_open, 1)
    render.write_text(r, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    final_render = render.read_text(encoding="utf-8")
    final_life = lifecycle.read_text(encoding="utf-8")
    required_source = (
        "bool g_frame_recording = false;",
        "unsigned g_active_frame_image_index = ~0u;",
        "VkResult g_active_frame_acquire_result = VK_SUCCESS;",
        "bool xr_vk_bootstrap_begin_frame()",
        "bool xr_vk_bootstrap_end_frame()",
        "void* xr_vk_bootstrap_active_command_buffer()",
        "g_active_frame_image_index = image_index;",
        "g_active_frame_acquire_result = acquire;",
        "g_frame_recording = true;",
        "g_vkCmdEndRenderPass(g_command_buffers[image_index])",
        "g_vkQueueSubmit",
        "g_vkQueuePresentKHR",
    )
    for token in required_source:
        if token not in final:
            raise RuntimeError(f"Vulkan frame lifecycle validation failed: missing {token}")
    for token in (
        '#include "vk_bootstrap.h"',
        "class xr_vk_render_frame_scope",
        "xr_vk_bootstrap_begin_frame()",
        "xr_vk_bootstrap_end_frame()",
        "xr_vk_render_frame_scope vk_frame_scope;",
    ):
        if token not in final_render:
            raise RuntimeError(f"Vulkan R2 frame scope validation failed: missing {token}")
    if "xr_vk_bootstrap_frame();" in final_life:
        raise RuntimeError("Vulkan frame lifecycle validation failed: stale OnFrame presentation hook remains")

    begin_pos = final.find("bool xr_vk_bootstrap_begin_frame()")
    end_pos = final.find("bool xr_vk_bootstrap_end_frame()")
    wrapper_pos = final.find("bool xr_vk_bootstrap_frame()", end_pos)
    if min(begin_pos, end_pos, wrapper_pos) < 0 or not begin_pos < end_pos < wrapper_pos:
        raise RuntimeError("Vulkan frame lifecycle validation failed: split frame order invalid")

    print("[vulkan-frame-lifecycle] R2 Render-scoped begin/end recording + active command buffer + RAII present installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep the Vulkan command buffer/render pass open across the real SHOC R2 Render phase.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
