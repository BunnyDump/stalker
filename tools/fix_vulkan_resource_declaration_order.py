from __future__ import annotations

import argparse
from pathlib import Path


def fix(root: Path) -> None:
    source = root.resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    declaration = "    void xr_vk_destroy_texture_object(XrVkTexture& texture);\n"
    if declaration not in text:
        marker = "    void xr_vk_reset_runtime_state()\n"
        if marker not in text:
            raise RuntimeError("Vulkan resource declaration-order marker not found")
        text = text.replace(marker, declaration + marker, 1)
        source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    if final.find(declaration) < 0 or final.find(declaration) > final.find("    void xr_vk_reset_runtime_state()"):
        raise RuntimeError("Vulkan texture destroy forward declaration remains after reset")
    print("[vulkan-resources] texture destroy helper declared before runtime reset")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fix generated Vulkan resource helper declaration order.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    fix(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
