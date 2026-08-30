from __future__ import annotations

import argparse
from pathlib import Path

VULKAN_CAPABILITY_POLICY = r'''	// Native Vulkan capability policy. Device/queue/surface validation is
	// performed by vk_bootstrap; legacy DX9 probing remains only in xrRender_R2.
	o.smapsize = 2048;
	o.mrt = TRUE;
	o.mrtmixdepth = TRUE;
	o.nullrt = FALSE;
	o.HW_smap_FETCH4 = FALSE;
	o.HW_smap = TRUE;
	o.HW_smap_PCF = TRUE;
	// Transitional storage field retained until the render-target ABI is neutralized.
	o.HW_smap_FORMAT = D3DFMT_D24X8;
	o.fp16_filter = TRUE;
	o.fp16_blend = TRUE;
	o.albedo_wo = FALSE;
	o.nvstencil = FALSE;
	o.nvdbt = FALSE;
	Msg("* [X-Ray Vulkan] native capability policy active");

'''


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")
    if "native capability policy active" in text:
        return

    start_marker = "\t// hardware\n"
    end_marker = "\t// options (smap-pool-size)\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("Vulkan R2 capability policy markers not found")

    legacy = text[start:end]
    required_legacy_tokens = (
        "HW.support(", "D3DRTYPE_SURFACE", "D3DUSAGE_RENDERTARGET",
        "D3DUSAGE_DEPTHSTENCIL", "D3DUSAGE_QUERY_FILTER",
        "D3DUSAGE_QUERY_POSTPIXELSHADER_BLENDING",
    )
    for token in required_legacy_tokens:
        if token not in legacy:
            raise RuntimeError(f"Vulkan R2 capability block changed upstream; missing {token}")

    text = text[:start] + VULKAN_CAPABILITY_POLICY + text[end:]
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    for token in ("native capability policy active", "o.mrt = TRUE", "o.HW_smap = TRUE", "o.fp16_blend = TRUE"):
        if token not in final:
            raise RuntimeError(f"Vulkan R2 capability validation missing {token}")
    for token in ("HW.support(", "D3DRTYPE_SURFACE", "D3DUSAGE_QUERY_POSTPIXELSHADER_BLENDING"):
        if token in final:
            raise RuntimeError(f"Vulkan R2 capability decoupling left legacy probe token {token}")
    print("[vulkan-r2-capabilities] DX9 hardware probing replaced with native Vulkan capability policy")


def main() -> int:
    ap = argparse.ArgumentParser(description="Remove DX9 capability probing from materialized xrRender_VK/r2.cpp.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
