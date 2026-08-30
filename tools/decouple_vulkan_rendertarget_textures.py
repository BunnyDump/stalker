from __future__ import annotations

import argparse
from pathlib import Path

ADAPTER_BLOCK = r'''
//////////////////////////////////////////////////////////////////////////
// Legacy procedural texture upload adapter. Render-target policy owns only
// logical texture setup; all D3DX allocation/lock/upload details live here.
static HRESULT xr_rt_legacy_build_material_lookup(IDirect3DVolumeTexture9*& texture)
{
    HRESULT hr = D3DXCreateVolumeTexture(HW.pDevice, TEX_material_LdotN, TEX_material_LdotH, 4, 1, 0,
        D3DFMT_A8L8, D3DPOOL_MANAGED, &texture);
    if (FAILED(hr))
        return hr;

    D3DLOCKED_BOX locked;
    hr = texture->LockBox(0, &locked, 0, 0);
    if (FAILED(hr))
        return hr;

    for (u32 slice = 0; slice < 4; ++slice)
    {
        for (u32 y = 0; y < TEX_material_LdotH; ++y)
        {
            for (u32 x = 0; x < TEX_material_LdotN; ++x)
            {
                u16* p = reinterpret_cast<u16*>(static_cast<LPBYTE>(locked.pBits) +
                    slice * locked.SlicePitch + y * locked.RowPitch + x * 2);
                float ld = float(x) / float(TEX_material_LdotN - 1);
                float ls = float(y) / float(TEX_material_LdotH - 1) + EPS_S;
                ls *= powf(ld, 1 / 32.f);
                float fd = 0.f;
                float fs = 0.f;

                switch (slice)
                {
                case 0:
                    fd = powf(ld, 0.75f);
                    fs = powf(ls, 16.f) * .5f;
                    break;
                case 1:
                    fd = powf(ld, 0.90f);
                    fs = powf(ls, 24.f);
                    break;
                case 2:
                    fd = ld;
                    fs = powf(ls * 1.01f, 128.f);
                    break;
                case 3:
                {
                    float s0 = _abs(1 - _abs(0.05f * _sin(33.f * ld) + ld - ls));
                    float s1 = _abs(1 - _abs(0.05f * _cos(33.f * ld * ls) + ld - ls));
                    float s2 = _abs(1 - _abs(ld - ls));
                    fd = ld;
                    fs = powf(_max(_max(s0, s1), s2), 24.f);
                    fs *= powf(ld, 1 / 7.f);
                    break;
                }
                default:
                    break;
                }

                s32 diffuse = clampr(iFloor(fd * 255.5f), 0, 255);
                s32 specular = clampr(iFloor(fs * 255.5f), 0, 255);
                if (y == TEX_material_LdotH - 1 && x == TEX_material_LdotN - 1)
                {
                    diffuse = 255;
                    specular = 255;
                }
                *p = u16(specular * 256 + diffuse);
            }
        }
    }

    return texture->UnlockBox(0);
}

static HRESULT xr_rt_legacy_build_jitter_textures(IDirect3DTexture9** textures)
{
    VERIFY(textures);
    D3DLOCKED_RECT locked[TEX_jitter_count];
    for (u32 it = 0; it < TEX_jitter_count; ++it)
    {
        HRESULT hr = D3DXCreateTexture(HW.pDevice, TEX_jitter, TEX_jitter, 1, 0,
            D3DFMT_Q8W8V8U8, D3DPOOL_MANAGED, &textures[it]);
        if (FAILED(hr))
            return hr;
        hr = textures[it]->LockRect(0, &locked[it], 0, 0);
        if (FAILED(hr))
            return hr;
    }

    for (u32 y = 0; y < TEX_jitter; ++y)
    {
        for (u32 x = 0; x < TEX_jitter; ++x)
        {
            DWORD data[TEX_jitter_count];
            generate_jitter(data, TEX_jitter_count);
            for (u32 it = 0; it < TEX_jitter_count; ++it)
            {
                u32* p = reinterpret_cast<u32*>(static_cast<LPBYTE>(locked[it].pBits) +
                    y * locked[it].Pitch + x * 4);
                *p = data[it];
            }
        }
    }

    for (u32 it = 0; it < TEX_jitter_count; ++it)
    {
        HRESULT hr = textures[it]->UnlockRect(0);
        if (FAILED(hr))
            return hr;
    }
    return S_OK;
}
//////////////////////////////////////////////////////////////////////////
'''

POLICY_BLOCK = r'''
	// Build textures
	{
		R_CHK(xr_rt_legacy_build_material_lookup(t_material_surf));
		t_material = Device.Resources->_CreateTexture(r2_material);
		t_material->surface_set(t_material_surf);

		R_CHK(xr_rt_legacy_build_jitter_textures(t_noise_surf));
		for (u32 it = 0; it < TEX_jitter_count; ++it)
		{
			string_path name;
			sprintf(name, "%s%d", r2_jitter, it);
			t_noise[it] = Device.Resources->_CreateTexture(name);
			t_noise[it]->surface_set(t_noise_surf[it]);
		}
	}
'''


def decouple(root: Path) -> None:
    path = root.resolve() / "xr_3da" / "xrRender_VK" / "r2_rendertarget.cpp"
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="strict")

    if "xr_rt_legacy_build_material_lookup" not in text:
        marker = "\nCRenderTarget::CRenderTarget()\n"
        if marker not in text:
            raise RuntimeError("render-target constructor marker not found")
        text = text.replace(marker, "\n" + ADAPTER_BLOCK + marker, 1)

    start = text.find("\t// Build textures\n")
    end = text.find("\n\t// PP\n", start)
    if start < 0 or end < 0:
        if POLICY_BLOCK.strip() not in text:
            raise RuntimeError("procedural texture policy block boundaries not found")
    else:
        current = text[start:end]
        if "D3DXCreate" in current or "D3DLOCKED_" in current:
            text = text[:start] + POLICY_BLOCK.rstrip("\n") + text[end:]

    path.write_text(text, encoding="utf-8")
    final = path.read_text(encoding="utf-8")
    for token in ("xr_rt_legacy_build_material_lookup", "xr_rt_legacy_build_jitter_textures"):
        if token not in final:
            raise RuntimeError(f"render-target procedural texture adapter missing {token}")

    start = final.find("\t// Build textures\n")
    end = final.find("\n\t// PP\n", start)
    policy = final[start:end]
    for token in ("D3DXCreate", "D3DLOCKED_", "D3DPOOL_", "LockBox", "LockRect", "UnlockBox", "UnlockRect"):
        if token in policy:
            raise RuntimeError(f"backend texture construction leaked into render-target policy: {token}")
    print("[vulkan-rendertarget-textures] procedural material/jitter upload isolated behind backend adapter")


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolate procedural render-target texture uploads behind backend adapter.")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    decouple(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
