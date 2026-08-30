#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

TEXT_EXTENSIONS={'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx','.inl','.ps','.vs','.gs','.hs','.ds','.cs','.glsl','.hlsl','.txt','.vcxproj','.props','.targets'}
D3D_PATTERNS={
 'd3d9_api':re.compile(r'\b(?:IDirect3D[A-Za-z0-9_]*|Direct3DCreate9(?:Ex)?|D3DPRESENT_PARAMETERS|D3DCAPS9|D3DADAPTER_IDENTIFIER9)\b',re.I),
 'd3d9_tokens':re.compile(r'\bD3D(?:FMT|USAGE|POOL|RS|TSS|SAMP|PT|QUERYTYPE|CLEAR|LOCK|DECL|TRANSFORMSTATE|TEXTURESTAGESTATETYPE|SAMPLERSTATETYPE|RENDERSTATETYPE|PRIMITIVETYPE|RESOURCE|DEVTYPE|CREATE|PRESENT|SWAPEFFECT|MULTISAMPLE|CMP|CULL|FILL|BLEND|BLENDOP|STENCILOP|FOG|SHADE|ZB|TADDRESS|TEXF|TA|TOP|DECLTYPE|DECLMETHOD|DECLUSAGE|FVF|PS_VERSION|VS_VERSION)_[A-Z0-9_]+\b'),
 'd3d_headers_libs':re.compile(r'\b(?:d3d9\.h|d3d9\.lib|d3dx9(?:\.h|\.lib)|d3dx9_[0-9]+\.dll)\b',re.I),
 'd3dx':re.compile(r'\bD3DX[A-Za-z0-9_]*\b'),
 'd3d10_11_dxgi':re.compile(r'\b(?:ID3D1[01][A-Za-z0-9_]*|D3D1[01]_[A-Z0-9_]+|IDXGI[A-Za-z0-9_]*|DXGI_[A-Z0-9_]+)\b',re.I),
 'd3dcompiler':re.compile(r'\b(?:D3DCompile|D3DReflect|D3DPreprocess|d3dcompiler(?:_[0-9]+)?(?:\.dll|\.lib))\b',re.I),
 'legacy_hw_device':re.compile(r'\bHW\.(?:pDevice|pD3D|Caps)\b'),
}
VULKAN_PATTERN=re.compile(r'\b(?:Vk[A-Z][A-Za-z0-9_]*|vk[A-Z][A-Za-z0-9_]*|VK_[A-Z0-9_]+|vulkan[\\/ ]vulkan\.h|vulkan-1(?:\.dll|\.lib))\b')

def main()->int:
 ap=argparse.ArgumentParser()
 ap.add_argument('source_root',type=Path)
 ap.add_argument('--json',dest='json_path',type=Path)
 ap.add_argument('--top',type=int,default=60)
 ap.add_argument('--fail-on-d3d',action='store_true')
 a=ap.parse_args()
 renderer=a.source_root.resolve()/'xr_3da'/'xrRender_VK'
 if not renderer.is_dir(): raise SystemExit(f'xrRender_VK not found: {renderer}')
 totals=Counter();hotspots=[];scanned=vk_files=d3d_files=0
 for p in renderer.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in TEXT_EXTENSIONS: continue
  scanned+=1;text=p.read_text(encoding='utf-8',errors='ignore');per=Counter()
  for n,pat in D3D_PATTERNS.items():
   c=len(pat.findall(text));totals[n]+=c
   if c: per[n]=c
  v=len(VULKAN_PATTERN.findall(text));totals['vulkan']+=v
  if v: vk_files+=1
  if per:
   d3d_files+=1
   hotspots.append({'file':p.relative_to(renderer).as_posix(),'d3d_references':sum(per.values()),'categories':dict(per),'vulkan_references':v})
 hotspots.sort(key=lambda x:(-x['d3d_references'],x['file']))
 report={'renderer':str(renderer),'files_scanned':scanned,'files_with_vulkan_references':vk_files,'files_with_direct3d_references':d3d_files,'direct3d_reference_count':sum(totals[n] for n in D3D_PATTERNS),'reference_totals':dict(totals),'hotspots':hotspots}
 print('=== X-Ray xrRender_VK migration audit ===')
 print(f'Text files scanned: {scanned}')
 print(f'Files containing Vulkan API tokens: {vk_files}')
 print(f'Files still containing Direct3D coupling: {d3d_files}')
 print(f'Vulkan token count: {totals.get("vulkan",0)}')
 print(f'Direct3D coupling token count: {report["direct3d_reference_count"]}')
 for n in D3D_PATTERNS: print(f'{n}: {totals.get(n,0)}')
 for row in hotspots[:max(a.top,0)]: print(f"  {row['file']}: {row['d3d_references']} {row['categories']}, vk={row['vulkan_references']}")
 if a.json_path:
  a.json_path.parent.mkdir(parents=True,exist_ok=True);a.json_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 if vk_files==0: raise SystemExit('Vulkan audit gate failed: no Vulkan API tokens in xrRender_VK')
 if a.fail_on_d3d and d3d_files: raise SystemExit(f'Vulkan audit gate failed: Direct3D coupling remains in {d3d_files} files')
 return 0
if __name__=='__main__': raise SystemExit(main())
