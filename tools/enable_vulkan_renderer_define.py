from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", MSBUILD_NS)
Q = lambda name: f"{{{MSBUILD_NS}}}{name}"
DEFINE = "XRRENDER_VULKAN"


def enable_renderer_define(root: Path) -> None:
    project = root.resolve() / "xr_3da" / "xrRender_VK" / "xrRender_VK.vcxproj"
    if not project.is_file():
        raise FileNotFoundError(project)
    tree = ET.parse(project)
    xml_root = tree.getroot()
    changed = 0
    groups = xml_root.findall(Q("ItemDefinitionGroup"))
    for group in groups:
        compile_node = group.find(Q("ClCompile"))
        if compile_node is None:
            continue
        defs = compile_node.find(Q("PreprocessorDefinitions"))
        if defs is None:
            defs = ET.SubElement(compile_node, Q("PreprocessorDefinitions"))
            defs.text = DEFINE + ";%(PreprocessorDefinitions)"
            changed += 1
            continue
        value = defs.text or ""
        tokens = [t.strip() for t in value.split(";")]
        if DEFINE not in tokens:
            defs.text = DEFINE + ";" + value
            changed += 1
    if not groups:
        raise RuntimeError("Vulkan renderer define: no ItemDefinitionGroup nodes found")
    tree.write(project, encoding="utf-8", xml_declaration=True)
    verify = project.read_text(encoding="utf-8", errors="ignore")
    if DEFINE not in verify:
        raise RuntimeError("Vulkan renderer define was not written to project")
    print(f"[vulkan-project] {DEFINE} enabled for xrRender_VK compile configurations; changed={changed}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add an explicit Vulkan renderer compile define to xrRender_VK.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    enable_renderer_define(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
