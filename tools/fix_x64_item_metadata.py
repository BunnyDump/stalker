from __future__ import annotations

import argparse
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", MSBUILD_NS)
COND_RE = re.compile(r"^'\$\(Configuration\)\|\$\(Platform\)'=='([^']+)\|Win32'$", re.I)


def normalize_project(path: Path) -> tuple[int, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    added = 0
    touched_items = 0

    # Old X-Ray projects store important per-file settings only for Win32:
    # PCH Create/NotUsing, ExcludedFromBuild, object names and warning overrides.
    # Copy those settings to the matching x64 configuration, but never overwrite
    # an explicit x64 setting introduced by the RC6 port.
    for parent in root.iter():
        children = list(parent)
        if not children:
            continue

        existing = {(child.tag, child.get("Condition")) for child in children}
        local_added = 0
        for child in children:
            cond = child.get("Condition")
            if not cond:
                continue
            match = COND_RE.match(cond.strip())
            if not match:
                continue

            config = match.group(1)
            x64_cond = f"'$(Configuration)|$(Platform)'=='{config}|x64'"
            key = (child.tag, x64_cond)
            if key in existing:
                continue

            clone = copy.deepcopy(child)
            clone.set("Condition", x64_cond)
            parent.append(clone)
            existing.add(key)
            added += 1
            local_added += 1

        if local_added:
            touched_items += 1

    if added:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return added, touched_items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone Win32 item-level MSBuild metadata to matching x64 configurations."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.root)
    projects = sorted(root.rglob("*.vcxproj"))
    changed = 0
    total_added = 0
    total_items = 0

    for project in projects:
        added, items = normalize_project(project)
        if added:
            changed += 1
            total_added += added
            total_items += items
            print(f"[x64-meta] {project}: +{added} metadata nodes across {items} items")

    print(
        f"[x64-meta] projects={len(projects)} changed={changed} "
        f"added={total_added} items={total_items}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
