from __future__ import annotations

import argparse
from pathlib import Path

MATH_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Renderer-neutral sun/shadow math. This replaces the legacy helper
// dependency while preserving the original row-vector matrix convention.
struct XrSunVec2
{
    float x, y;
    XrSunVec2() {}
    XrSunVec2(float _x, float _y) : x(_x), y(_y) {}
    XrSunVec2 operator+(const XrSunVec2& v) const { return XrSunVec2(x + v.x, y + v.y); }
    XrSunVec2 operator-(const XrSunVec2& v) const { return XrSunVec2(x - v.x, y - v.y); }
    XrSunVec2 operator*(float s) const { return XrSunVec2(x * s, y * s); }
};
static inline XrSunVec2 operator*(float s, const XrSunVec2& v) { return v * s; }

struct XrSunVec3
{
    float x, y, z;
    XrSunVec3() {}
    XrSunVec3(float _x, float _y, float _z) : x(_x), y(_y), z(_z) {}
    XrSunVec3 operator+(const XrSunVec3& v) const { return XrSunVec3(x + v.x, y + v.y, z + v.z); }
    XrSunVec3 operator-(const XrSunVec3& v) const { return XrSunVec3(x - v.x, y - v.y, z - v.z); }
    XrSunVec3 operator-() const { return XrSunVec3(-x, -y, -z); }
    XrSunVec3 operator*(float s) const { return XrSunVec3(x * s, y * s, z * s); }
    XrSunVec3& operator+=(const XrSunVec3& v) { x += v.x; y += v.y; z += v.z; return *this; }
};
static inline XrSunVec3 operator*(float s, const XrSunVec3& v) { return v * s; }

struct XrSunVec4
{
    float x, y, z, w;
    XrSunVec4() {}
    XrSunVec4(float _x, float _y, float _z, float _w) : x(_x), y(_y), z(_z), w(_w) {}
    XrSunVec4 operator+(const XrSunVec4& v) const { return XrSunVec4(x + v.x, y + v.y, z + v.z, w + v.w); }
    XrSunVec4 operator-(const XrSunVec4& v) const { return XrSunVec4(x - v.x, y - v.y, z - v.z, w - v.w); }
    XrSunVec4 operator*(float s) const { return XrSunVec4(x * s, y * s, z * s, w * s); }
};
static inline XrSunVec4 operator*(float s, const XrSunVec4& v) { return v * s; }

struct XrSunPlane
{
    float a, b, c, d;
    XrSunPlane() {}
    XrSunPlane(float _a, float _b, float _c, float _d) : a(_a), b(_b), c(_c), d(_d) {}
};

struct XrSunMatrix
{
    float _11, _12, _13, _14;
    float _21, _22, _23, _24;
    float _31, _32, _33, _34;
    float _41, _42, _43, _44;
    XrSunMatrix() {}
    XrSunMatrix(float m11,float m12,float m13,float m14,
        float m21,float m22,float m23,float m24,
        float m31,float m32,float m33,float m34,
        float m41,float m42,float m43,float m44)
        : _11(m11),_12(m12),_13(m13),_14(m14),
          _21(m21),_22(m22),_23(m23),_24(m24),
          _31(m31),_32(m32),_33(m33),_34(m34),
          _41(m41),_42(m42),_43(m43),_44(m44) {}
};

static inline float xr_sun_vec2_dot(const XrSunVec2* a, const XrSunVec2* b)
{ return a->x*b->x + a->y*b->y; }
static inline float xr_sun_vec2_length(const XrSunVec2* v)
{ return _sqrt(v->x*v->x + v->y*v->y); }
static inline float xr_sun_vec3_dot(const XrSunVec3* a, const XrSunVec3* b)
{ return a->x*b->x + a->y*b->y + a->z*b->z; }
static inline XrSunVec3* xr_sun_vec3_cross(XrSunVec3* out, const XrSunVec3* a, const XrSunVec3* b)
{
    XrSunVec3 r(a->y*b->z-a->z*b->y, a->z*b->x-a->x*b->z, a->x*b->y-a->y*b->x);
    *out=r; return out;
}
static inline XrSunVec3* xr_sun_vec3_normalize(XrSunVec3* out, const XrSunVec3* in)
{
    const float len=_sqrt(in->x*in->x+in->y*in->y+in->z*in->z);
    if (len>EPS_S) { const float s=1.f/len; *out=XrSunVec3(in->x*s,in->y*s,in->z*s); }
    else *out=XrSunVec3(0.f,0.f,0.f);
    return out;
}
static inline float xr_sun_plane_dot_coord(const XrSunPlane* p, const XrSunVec3* v)
{ return p->a*v->x+p->b*v->y+p->c*v->z+p->d; }
static inline float xr_sun_plane_dot_normal(const XrSunPlane* p, const XrSunVec3* v)
{ return p->a*v->x+p->b*v->y+p->c*v->z; }

static inline XrSunMatrix* xr_sun_matrix_multiply(XrSunMatrix* out, const XrSunMatrix* a, const XrSunMatrix* b)
{
    XrSunMatrix r;
    const float* A=&a->_11; const float* B=&b->_11; float* R=&r._11;
    for (int row=0; row<4; ++row)
        for (int col=0; col<4; ++col)
            R[row*4+col]=A[row*4+0]*B[0*4+col]+A[row*4+1]*B[1*4+col]+
                         A[row*4+2]*B[2*4+col]+A[row*4+3]*B[3*4+col];
    *out=r; return out;
}

static inline XrSunMatrix* xr_sun_matrix_inverse(XrSunMatrix* out, float* determinant, const XrSunMatrix* in)
{
    float a[4][8];
    const float* src=&in->_11;
    for (int r=0;r<4;++r) for (int c=0;c<4;++c) a[r][c]=src[r*4+c];
    for (int r=0;r<4;++r) for (int c=0;c<4;++c) a[r][4+c]=(r==c)?1.f:0.f;
    float det=1.f;
    for (int c=0;c<4;++c)
    {
        int pivot=c;
        float best=_abs(a[c][c]);
        for (int r=c+1;r<4;++r) if (_abs(a[r][c])>best) { best=_abs(a[r][c]); pivot=r; }
        if (best<1e-12f) return NULL;
        if (pivot!=c) { for (int k=0;k<8;++k) { float t=a[c][k]; a[c][k]=a[pivot][k]; a[pivot][k]=t; } det=-det; }
        const float p=a[c][c]; det*=p; const float invp=1.f/p;
        for (int k=0;k<8;++k) a[c][k]*=invp;
        for (int r=0;r<4;++r) if (r!=c)
        {
            const float f=a[r][c];
            for (int k=0;k<8;++k) a[r][k]-=f*a[c][k];
        }
    }
    float* dst=&out->_11;
    for (int r=0;r<4;++r) for (int c=0;c<4;++c) dst[r*4+c]=a[r][4+c];
    if (determinant) *determinant=det;
    return out;
}

static inline XrSunMatrix* xr_sun_matrix_translation(XrSunMatrix* out, float x,float y,float z)
{
    *out=XrSunMatrix(1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1); return out;
}
static inline XrSunMatrix* xr_sun_matrix_ortho_off_center_lh(XrSunMatrix* out,
    float l,float r,float b,float t,float zn,float zf)
{
    *out=XrSunMatrix(2.f/(r-l),0,0,0, 0,2.f/(t-b),0,0, 0,0,1.f/(zf-zn),0,
        (l+r)/(l-r),(t+b)/(b-t),zn/(zn-zf),1.f);
    return out;
}
static inline XrSunVec3* xr_sun_vec3_transform_normal(XrSunVec3* out, const XrSunVec3* v, const XrSunMatrix* m)
{
    XrSunVec3 r(v->x*m->_11+v->y*m->_21+v->z*m->_31,
                v->x*m->_12+v->y*m->_22+v->z*m->_32,
                v->x*m->_13+v->y*m->_23+v->z*m->_33);
    *out=r; return out;
}
static inline XrSunVec3 xr_sun_transform_coord_value(const XrSunVec3& v,const XrSunMatrix& m)
{
    const float x=v.x*m._11+v.y*m._21+v.z*m._31+m._41;
    const float y=v.x*m._12+v.y*m._22+v.z*m._32+m._42;
    const float z=v.x*m._13+v.y*m._23+v.z*m._33+m._43;
    const float w=v.x*m._14+v.y*m._24+v.z*m._34+m._44;
    const float invw=(w!=0.f)?1.f/w:1.f;
    return XrSunVec3(x*invw,y*invw,z*invw);
}
static inline XrSunVec3* xr_sun_vec3_transform_coord_array(XrSunVec3* out, UINT out_stride,
    const XrSunVec3* in, UINT in_stride, const XrSunMatrix* m, UINT count)
{
    u8* dst=reinterpret_cast<u8*>(out); const u8* src=reinterpret_cast<const u8*>(in);
    for (UINT i=0;i<count;++i)
    {
        const XrSunVec3 value=*reinterpret_cast<const XrSunVec3*>(src+i*in_stride);
        *reinterpret_cast<XrSunVec3*>(dst+i*out_stride)=xr_sun_transform_coord_value(value,*m);
    }
    return out;
}
//////////////////////////////////////////////////////////////////////////
'''

REPLACEMENTS = (
    ("D3DXMATRIX", "XrSunMatrix"),
    ("D3DXPLANE", "XrSunPlane"),
    ("D3DXVECTOR2", "XrSunVec2"),
    ("D3DXVECTOR3", "XrSunVec3"),
    ("D3DXVECTOR4", "XrSunVec4"),
    ("D3DXVec2Dot", "xr_sun_vec2_dot"),
    ("D3DXVec2Length", "xr_sun_vec2_length"),
    ("D3DXVec3Cross", "xr_sun_vec3_cross"),
    ("D3DXVec3Dot", "xr_sun_vec3_dot"),
    ("D3DXVec3Normalize", "xr_sun_vec3_normalize"),
    ("D3DXVec3TransformNormal", "xr_sun_vec3_transform_normal"),
    ("D3DXVec3TransformCoordArray", "xr_sun_vec3_transform_coord_array"),
    ("D3DXPlaneDotCoord", "xr_sun_plane_dot_coord"),
    ("D3DXPlaneDotNormal", "xr_sun_plane_dot_normal"),
    ("D3DXMatrixMultiply", "xr_sun_matrix_multiply"),
    ("D3DXMatrixInverse", "xr_sun_matrix_inverse"),
    ("D3DXMatrixOrthoOffCenterLH", "xr_sun_matrix_ortho_off_center_lh"),
    ("D3DXMatrixTranslation", "xr_sun_matrix_translation"),
)


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_R_sun.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")
    if "struct XrSunMatrix" in text:
        return
    marker = "#define IS_SPECIAL(F) ((FLT_AS_DW(F) & 0x7f800000L) == 0x7f800000L)\n"
    if marker not in text:
        raise RuntimeError("sun math insertion marker not found")
    text = text.replace(marker, marker + MATH_BLOCK, 1)
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    text = text.replace("D3D uses [0..1] range for Z", "the renderer clip space uses [0..1] range for Z")
    text = text.replace("Prepare to interact with D3DX code", "Prepare renderer-neutral TSM math")
    text = text.replace("D3DX code", "legacy helper math")
    path.write_text(text, encoding="utf-8")

    final = path.read_text(encoding="utf-8")
    leftovers = [token for token in ("D3DX", "IDirect3D", "D3DFMT_", "D3DCMP_", "D3DPT_") if token in final]
    if leftovers:
        raise RuntimeError(f"sun math decoupling left Direct3D tokens: {leftovers}")
    for token in ("XrSunMatrix", "xr_sun_matrix_inverse", "xr_sun_vec3_transform_coord_array"):
        if token not in final:
            raise RuntimeError(f"sun math validation missing {token}")
    print("[vulkan-sun-math] r2_R_sun.cpp now uses renderer-neutral shadow math")


def main() -> int:
    ap = argparse.ArgumentParser(description="Replace legacy sun helper math with renderer-neutral math.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
