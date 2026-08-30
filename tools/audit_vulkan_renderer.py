#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

TEXT_EXTENSIONS = {'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx','.inl','.ps','.vs','.gs','.hs','.ds','.cs','.glsl','.hlsl','.txt','.vcxproj','.props','.targets'}
D3D_PATTERNS = {
    'd3d9_types': re.compile(r'\b(?:IDirect3D[A-Za-z0-9_]*|D3D[A-Z0-9_]*|Direct3DCreate9(?:Ex)?)\b'),
    'd3d9_headers_libs': re.compile(r'\b(?:d3d9\.h|d3d9\.lib|d3dx9(?:_[0-9]+)?\.lib|d3dx9\.h)\b', re.I),
    'd3d10': re.compile(r'\b(?:ID3D10[A-Za-z0-9_]*|D3D10_[A-Z0-9_]*|d3d10\.h|d3d10\.lib)\b', re.I),
    'd3d11': re.compile(r'\b(?:ID3D11[A-Za-z0-9_]*|D3D11_[A-Z0-9_]*|d3d11\.h|d3d11\.lib)\b', re.I),
    'dxgi': re.compile(r'\b(?:IDXGI[A-Za-z0-9_]*|DXGI_[A-Z0-9_]*|dxgi\.h|dxgi\.lib)\b', re.I),
    'd3dcompiler': re.compile(r'\b(?:D3DCompile[A-Za-z0-9_]*|D3DReflect|ID3DBlob|d3dcompiler(?:_[0-9]+)?\.dll|d3dcompiler(?:_[0-9]+)?\.lib)\b', re.I),
}
VULKAN_PATTERN = re.compile(r'\b(?:Vk[A-Z][A-Za-z0-9_]*|vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+|vulkan[\\/ ]vulkan\.h|vulkan-1(?:\.dll|\.lib))\b')


def scan_tree(root: Path, label: str) -> dict:
    totals = Counter(); hotspots=[]; scanned=vk_files=d3d_files=0
    if not root.is_dir():
        return {'label': label, 'root': str(root), 'missing': True, 'files_scanned': 0, 'files_with_vulkan_references': 0,
                'files_with_direct3d_references': 0, 'reference_totals': {}, 'hotspots': []}
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        scanned += 1
        text = p.read_text(encoding='utf-8', errors='ignore')
        per = Counter()
        for name, pat in D3D_PATTERNS.items():
            count = len(pat.findall(text)); totals[name] += count
            if count: per[name] = count
        vk = len(VULKAN_PATTERN.findall(text)); totals['vulkan'] += vk
        if vk: vk_files += 1
        if per:
            d3d_files += 1
            hotspots.append({'file': p.relative_to(root).as_posix(), 'd3d_references': sum(per.values()),
                             'categories': dict(per), 'vulkan_references': vk})
    hotspots.sort(key=lambda row: (-row['d3d_references'], row['file']))
    return {'label': label, 'root': str(root), 'missing': False, 'files_scanned': scanned,
            'files_with_vulkan_references': vk_files, 'files_with_direct3d_references': d3d_files,
            'reference_totals': dict(totals), 'hotspots': hotspots}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('source_root', type=Path)
    ap.add_argument('--json', dest='json_path', type=Path)
    ap.add_argument('--top', type=int, default=30)
    args = ap.parse_args()
    source = args.source_root.resolve()
    renderer = source / 'xr_3da' / 'xrRender_VK'
    shared = source / 'xr_3da' / 'xrRender'
    if not renderer.is_dir():
        raise SystemExit(f'xrRender_VK not found: {renderer}')

    direct = scan_tree(renderer, 'xrRender_VK')
    shared_report = scan_tree(shared, 'xrRender shared layer')
    combined = Counter()
    for report in (direct, shared_report):
        combined.update(report['reference_totals'])

    report = {
        'source_root': str(source),
        'direct_renderer': direct,
        'shared_renderer': shared_report,
        'combined_reference_totals': dict(combined),
    }
    print('=== X-Ray Vulkan renderer coupling audit ===')
    for section in (direct, shared_report):
        print(f"[{section['label']}] scanned={section['files_scanned']} d3d_files={section['files_with_direct3d_references']} vk_files={section['files_with_vulkan_references']}")
        print('  totals:', section['reference_totals'])
        for row in section['hotspots'][:max(args.top, 0)]:
            print(f"  {row['file']}: {row['d3d_references']} {row['categories']}, vk={row['vulkan_references']}")
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    if direct['files_with_vulkan_references'] == 0:
        raise SystemExit('Vulkan audit gate failed: no Vulkan API tokens in xrRender_VK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
