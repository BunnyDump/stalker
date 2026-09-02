from __future__ import annotations

import argparse
import re
from pathlib import Path


SCOPE_MARKER = "class xr_vk_render_frame_scope"
FRAME_INSTANCE = "xr_vk_render_frame_scope vk_render_frame_scope;"


def _read(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text, newline


def install_render_scope(root: Path) -> None:
    renderer = root.resolve() / "xr_3da" / "xrRender_VK"
    render_source = renderer / "r2_R_render.cpp"
    lifecycle_source = renderer / "r2.cpp"

    if not render_source.is_file() or not lifecycle_source.is_file():
        raise FileNotFoundError("Vulkan render scope requires materialized xrRender_VK sources")

    text, nl = _read(render_source)

    include_block = (
        '#include "stdafx.h"' + nl +
        '#ifdef XRAY_VULKAN_RUNTIME' + nl +
        '#include "vk_bootstrap.h"' + nl +
        '#endif'
    )
    if '#include "vk_bootstrap.h"' not in text:
        include_marker = '#include "stdafx.h"'
        if include_marker not in text:
            raise RuntimeError("Vulkan render scope: stdafx include marker not found")
        text = text.replace(include_marker, include_block, 1)

    if SCOPE_MARKER not in text:
        anchor = "IC bool pred_sp_sort"
        pos = text.find(anchor)
        if pos < 0:
            raise RuntimeError("Vulkan render scope: pred_sp_sort anchor not found")
        scope = (
            "#ifdef XRAY_VULKAN_RUNTIME" + nl +
            "namespace" + nl +
            "{" + nl +
            "    class xr_vk_render_frame_scope" + nl +
            "    {" + nl +
            "    public:" + nl +
            "        xr_vk_render_frame_scope()" + nl +
            '            : armed_(xr_vk_bootstrap_runtime_ready() && strstr(Core.Params, "-vkpresent") != 0)' + nl +
            "        {" + nl +
            "        }" + nl + nl +
            "        ~xr_vk_render_frame_scope()" + nl +
            "        {" + nl +
            "            if (armed_ && xr_vk_bootstrap_runtime_ready())" + nl +
            "                xr_vk_bootstrap_frame();" + nl +
            "        }" + nl + nl +
            "    private:" + nl +
            "        bool armed_;" + nl +
            "    };" + nl +
            "}" + nl +
            "#endif" + nl + nl
        )
        text = text[:pos] + scope + text[pos:]

    if FRAME_INSTANCE not in text:
        pattern = r"(void\s+CRender::Render\(\)\s*\r?\n\{\s*\r?\n)"
        hook = (
            "#ifdef XRAY_VULKAN_RUNTIME" + nl +
            "    xr_vk_render_frame_scope vk_render_frame_scope;" + nl +
            "#endif" + nl + nl
        )
        text, count = re.subn(pattern, lambda m: m.group(1) + hook, text, count=1)
        if count != 1:
            raise RuntimeError("Vulkan render scope: CRender::Render entry not found")

    render_source.write_text(text, encoding="utf-8")

    lifecycle, lifecycle_nl = _read(lifecycle_source)
    old_hook = re.compile(
        r'\tif \(xr_vk_bootstrap_runtime_ready\(\) && strstr\(Core\.Params, "-vkpresent"\)\)\r?\n'
        r'\t\txr_vk_bootstrap_frame\(\);\r?\n(?:\r?\n)?'
    )
    lifecycle, removed = old_hook.subn("", lifecycle, count=1)

    # Idempotency: if a prior run already removed the hook, do not fail.
    if removed == 0 and "xr_vk_bootstrap_frame();" in lifecycle:
        raise RuntimeError("Vulkan render scope: an unexpected bootstrap-frame call remains in r2.cpp")

    lifecycle_source.write_text(lifecycle, encoding="utf-8")

    final = render_source.read_text(encoding="utf-8")
    final_lifecycle = lifecycle_source.read_text(encoding="utf-8")
    required = (
        '#include "vk_bootstrap.h"',
        SCOPE_MARKER,
        'strstr(Core.Params, "-vkpresent") != 0',
        "if (armed_ && xr_vk_bootstrap_runtime_ready())",
        "xr_vk_bootstrap_frame();",
        FRAME_INSTANCE,
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"Vulkan render scope validation failed: missing {token}")

    if final.count(FRAME_INSTANCE) != 1:
        raise RuntimeError("Vulkan render scope validation failed: duplicate CRender::Render scope")
    if "xr_vk_bootstrap_frame();" in final_lifecycle:
        raise RuntimeError("Vulkan render scope validation failed: legacy CRender::OnFrame presentation remains")

    print("[vulkan-render-scope] presentation ownership moved from OnFrame to RAII CRender::Render scope")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move the transitional Vulkan frame/present hook onto the real xrRender_R2 render callback."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    install_render_scope(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
