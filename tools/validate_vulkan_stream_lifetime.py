from __future__ import annotations

import argparse
from pathlib import Path


def validate(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    text = source.read_text(encoding="utf-8")

    required = (
        "bool g_frame_submission_pending = false;",
        "bool xr_vk_wait_for_stream_write_safety()",
        "g_frame_submission_pending = true;",
        "xr_vk_create_buffer(67108864ull",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"Vulkan stream lifetime validation failed: missing {token}")

    resize_start = text.index("bool xr_vk_resize_host_stream")
    resize_end = text.index("bool xr_vk_upload_host_stream", resize_start)
    resize = text[resize_start:resize_end]
    if "xr_vk_wait_for_stream_write_safety()" not in resize:
        raise RuntimeError("Vulkan stream lifetime validation failed: resize is not fence guarded")

    upload_start = resize_end
    upload_end = text.index("bool xr_vk_upload_vertex_stream", upload_start)
    upload = text[upload_start:upload_end]
    if "xr_vk_wait_for_stream_write_safety()" not in upload:
        raise RuntimeError("Vulkan stream lifetime validation failed: upload is not fence guarded")

    frame_start = text.index("bool xr_vk_bootstrap_begin_frame()")
    frame_end = text.index("bool xr_vk_bootstrap_frame()", frame_start)
    frame = text[frame_start:frame_end]
    wait = frame.index("g_vkWaitForFences")
    clear = frame.index("g_frame_submission_pending = false;", wait)
    submit = frame.index("g_vkQueueSubmit")
    pending = frame.index("g_frame_submission_pending = true;", submit)
    if not wait < clear < submit < pending:
        raise RuntimeError("Vulkan stream lifetime validation failed: submission state order is unsafe")

    print("[vulkan-stream-lifetime] fence-guarded stream writes + 64 MiB staging verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    validate(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
