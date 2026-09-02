from __future__ import annotations

import argparse
from pathlib import Path


def harden(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    source = renderer / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError("Vulkan stream lifetime hardening requires materialized stream mirror")

    text = source.read_text(encoding="utf-8")

    state_marker = "    VkFence g_frame_fence = VK_NULL_HANDLE;\n"
    if "g_frame_submission_pending" not in text:
        if state_marker not in text:
            raise RuntimeError("Vulkan stream lifetime: frame fence state marker not found")
        text = text.replace(
            state_marker,
            state_marker + "    bool g_frame_submission_pending = false;\n",
            1,
        )

    helper_marker = "    void xr_vk_destroy_stream_buffer(VkBuffer& buffer, VkDeviceMemory& memory, VkDeviceSize& capacity)\n"
    helper = r'''    bool xr_vk_wait_for_stream_write_safety()
    {
        if (!g_frame_submission_pending)
            return true;
        if (g_device == VK_NULL_HANDLE || g_frame_fence == VK_NULL_HANDLE || !g_vkWaitForFences)
            return false;
        if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
            return false;
        g_frame_submission_pending = false;
        return true;
    }

'''
    if "xr_vk_wait_for_stream_write_safety" not in text:
        if helper_marker not in text:
            raise RuntimeError("Vulkan stream lifetime: stream helper marker not found")
        text = text.replace(helper_marker, helper + helper_marker, 1)

    resize_guard = '''        if (!required || g_device == VK_NULL_HANDLE)
            return false;
'''
    resize_replacement = '''        if (!required || g_device == VK_NULL_HANDLE)
            return false;
        if (!xr_vk_wait_for_stream_write_safety())
            return false;
'''
    start = text.find("bool xr_vk_resize_host_stream")
    if start < 0:
        raise RuntimeError("Vulkan stream lifetime: resize helper not found")
    end = text.find("bool xr_vk_upload_host_stream", start)
    resize = text[start:end]
    if "xr_vk_wait_for_stream_write_safety()" not in resize:
        if resize_guard not in resize:
            raise RuntimeError("Vulkan stream lifetime: resize guard marker not found")
        resize = resize.replace(resize_guard, resize_replacement, 1)
        text = text[:start] + resize + text[end:]

    upload_guard = '''        if (!data || !byte_count)
            return false;
'''
    upload_replacement = '''        if (!data || !byte_count)
            return false;
        if (!xr_vk_wait_for_stream_write_safety())
            return false;
'''
    start = text.find("bool xr_vk_upload_host_stream")
    if start < 0:
        raise RuntimeError("Vulkan stream lifetime: upload helper not found")
    end = text.find("bool xr_vk_upload_vertex_stream", start)
    upload = text[start:end]
    if "xr_vk_wait_for_stream_write_safety()" not in upload:
        if upload_guard not in upload:
            raise RuntimeError("Vulkan stream lifetime: upload guard marker not found")
        upload = upload.replace(upload_guard, upload_replacement, 1)
        text = text[:start] + upload + text[end:]

    frame_start = text.find("bool xr_vk_bootstrap_frame()")
    frame_end = text.find("bool xr_vk_bootstrap_runtime_ready()", frame_start)
    if frame_start < 0 or frame_end < 0:
        raise RuntimeError("Vulkan stream lifetime: frame function not found")
    frame = text[frame_start:frame_end]

    wait_marker = '''    if (g_vkWaitForFences(g_device, 1, &g_frame_fence, VK_TRUE, ~0ull) != VK_SUCCESS)
        return false;
'''
    wait_replacement = wait_marker + "    g_frame_submission_pending = false;\n"
    if "g_frame_submission_pending = false;" not in frame:
        if wait_marker not in frame:
            raise RuntimeError("Vulkan stream lifetime: frame wait marker not found")
        frame = frame.replace(wait_marker, wait_replacement, 1)

    submit_marker = '''    if (g_vkQueueSubmit(g_graphics_queue, 1, &submit, g_frame_fence) != VK_SUCCESS)
'''
    # Hardened frame-fence layer may wrap the failure body, so only insert after the complete submit failure block.
    submit_index = frame.find(submit_marker)
    if submit_index < 0:
        raise RuntimeError("Vulkan stream lifetime: queue submit marker not found")
    if "g_frame_submission_pending = true;" not in frame:
        body_start = submit_index + len(submit_marker)
        # Find the next blank line after the failure branch; this is stable across the current fence hardening.
        insert_at = frame.find("\n\n", body_start)
        if insert_at < 0:
            raise RuntimeError("Vulkan stream lifetime: cannot locate queue-submit branch end")
        frame = frame[: insert_at + 2] + "    g_frame_submission_pending = true;\n\n" + frame[insert_at + 2 :]

    text = text[:frame_start] + frame + text[frame_end:]

    destroy_start = text.find("void xr_vk_destroy_frame_resources()")
    if destroy_start < 0:
        raise RuntimeError("Vulkan stream lifetime: destroy function not found")
    destroy_end = text.find("void xr_vk_destroy_window_runtime()", destroy_start)
    destroy = text[destroy_start:destroy_end]
    reset_marker = "        g_frame_fence = VK_NULL_HANDLE;\n"
    if "g_frame_submission_pending = false;" not in destroy:
        if reset_marker not in destroy:
            raise RuntimeError("Vulkan stream lifetime: fence reset marker not found")
        destroy = destroy.replace(reset_marker, reset_marker + "        g_frame_submission_pending = false;\n", 1)
        text = text[:destroy_start] + destroy + text[destroy_end:]

    source.write_text(text, encoding="utf-8")

    final = source.read_text(encoding="utf-8")
    required = (
        "bool g_frame_submission_pending = false;",
        "bool xr_vk_wait_for_stream_write_safety()",
        "if (!g_frame_submission_pending)",
        "g_frame_submission_pending = true;",
        "g_frame_submission_pending = false;",
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan stream lifetime validation failed: missing {token}")

    resize_start = final.index("bool xr_vk_resize_host_stream")
    resize_end = final.index("bool xr_vk_upload_host_stream", resize_start)
    if "xr_vk_wait_for_stream_write_safety()" not in final[resize_start:resize_end]:
        raise RuntimeError("Vulkan stream lifetime validation failed: resize can destroy in-flight buffers")
    upload_start = resize_end
    upload_end = final.index("bool xr_vk_upload_vertex_stream", upload_start)
    if "xr_vk_wait_for_stream_write_safety()" not in final[upload_start:upload_end]:
        raise RuntimeError("Vulkan stream lifetime validation failed: upload can overwrite in-flight buffers")

    print("[vulkan-stream-lifetime] fence-guarded vertex/index host writes and resize destruction installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prevent Vulkan dynamic stream overwrite/destruction while GPU work is in flight.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
