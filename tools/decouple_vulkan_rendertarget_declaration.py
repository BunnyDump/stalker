from __future__ import annotations

import argparse
from pathlib import Path

DECL_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral vertex declaration for helper passes. The D3D9 adapter
// translates this logical FLOAT4 POSITION layout only at the fallback edge.
enum XrRtVertexSemantic
{
    XR_RT_SEMANTIC_POSITION
};

struct XrRtVertexElement
{
    u16 offset;
    u8 components;
    XrRtVertexSemantic semantic;
};

static inline const D3DVERTEXELEMENT9* xr_rt_legacy_vertex_declaration(const XrRtVertexElement* elements, u32 count)
{
    static D3DVERTEXELEMENT9 declaration[8];
    VERIFY(elements);
    VERIFY(count < 8);
    for (u32 i = 0; i < count; ++i)
    {
        VERIFY(elements[i].components == 4);
        VERIFY(elements[i].semantic == XR_RT_SEMANTIC_POSITION);
        declaration[i].Stream = 0;
        declaration[i].Offset = elements[i].offset;
        declaration[i].Type = D3DDECLTYPE_FLOAT4;
        declaration[i].Method = D3DDECLMETHOD_DEFAULT;
        declaration[i].Usage = D3DDECLUSAGE_POSITION;
        declaration[i].UsageIndex = 0;
    }
    declaration[count] = D3DDECL_END();
    return declaration;
}
//////////////////////////////////////////////////////////////////////////
'''

OLD_DECL = r'''static D3DVERTEXELEMENT9 dwDecl[] = {
			{0, 0, D3DDECLTYPE_FLOAT4, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_POSITION, 0}, // pos+uv
			D3DDECL_END()};'''
NEW_DECL = r'''static const XrRtVertexElement combine_elements[] = {
            {0, 4, XR_RT_SEMANTIC_POSITION}};'''
OLD_CREATE = "g_combine_VP.create(dwDecl, RCache.Vertex.Buffer(), RCache.QuadIB);"
NEW_CREATE = "g_combine_VP.create(xr_rt_legacy_vertex_declaration(combine_elements, sizeof(combine_elements) / sizeof(combine_elements[0])), RCache.Vertex.Buffer(), RCache.QuadIB);"


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")

    if "struct XrRtVertexElement" not in text:
        marker = "//////////////////////////////////////////////////////////////////////////\n// Renderer-neutral vertex-layout vocabulary for render-target helper geometry."
        pos = text.find(marker)
        if pos < 0:
            raise RuntimeError("renderer-neutral FVF block missing before declaration decoupling")
        close = text.find("//////////////////////////////////////////////////////////////////////////", pos + len(marker))
        close = text.find("\n", close) + 1
        text = text[:close] + DECL_BLOCK + text[close:]

    if OLD_DECL in text:
        text = text.replace(OLD_DECL, NEW_DECL, 1)
    elif "combine_elements" not in text:
        raise RuntimeError("combine D3D vertex declaration marker not found")

    if OLD_CREATE in text:
        text = text.replace(OLD_CREATE, NEW_CREATE, 1)
    elif NEW_CREATE not in text:
        raise RuntimeError("combine geometry creation marker not found")

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("struct XrRtVertexElement", "combine_elements", "xr_rt_legacy_vertex_declaration"):
        if token not in final:
            raise RuntimeError(f"render-target declaration validation missing {token}")

    adapter_end = final.find("//////////////////////////////////////////////////////////////////////////", final.find("struct XrRtVertexElement") + 1)
    body = final[adapter_end + len("//////////////////////////////////////////////////////////////////////////"):]
    for token in ("static D3DVERTEXELEMENT9 dwDecl[]", "D3DDECLTYPE_FLOAT4", "const D3DVERTEXELEMENT9* dwDecl"):
        if token in body:
            raise RuntimeError(f"direct D3D vertex declaration remains in render-target policy: {token}")
    print("[vulkan-rendertarget-declaration] combine vertex declaration centralized behind renderer-neutral layout")


def main() -> int:
    ap = argparse.ArgumentParser(description="Centralize render-target vertex declarations behind renderer-neutral vocabulary.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
