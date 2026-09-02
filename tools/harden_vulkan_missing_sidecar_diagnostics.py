from __future__ import annotations

import argparse
from pathlib import Path


HELPERS = r'''    struct xr_vk_missing_sidecar_record
    {
        u64 identity;
        bool vertex_stage;
    };

    xr_vector<xr_vk_missing_sidecar_record> g_missing_sidecars;

    void xr_vk_log_missing_shader_sidecar(const char* stage, u64 identity)
    {
        if (!stage || !identity)
            return;
        const bool vertex_stage = strcmp(stage, "vs") == 0;
        if (!vertex_stage && strcmp(stage, "ps") != 0)
            return;
        for (u32 i = 0; i < g_missing_sidecars.size(); ++i)
            if (g_missing_sidecars[i].identity == identity &&
                g_missing_sidecars[i].vertex_stage == vertex_stage)
                return;

        xr_vk_missing_sidecar_record record;
        record.identity = identity;
        record.vertex_stage = vertex_stage;
        g_missing_sidecars.push_back(record);

        char line[96] = {};
        const int length = _snprintf_s(line, sizeof(line), _TRUNCATE,
            "%s_%016I64x.spv\r\n", stage, static_cast<unsigned __int64>(identity));
        if (length <= 0)
            return;
        HANDLE log = CreateFileA("vulkan_missing_sidecars.log", FILE_APPEND_DATA,
            FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (log == INVALID_HANDLE_VALUE)
            return;
        DWORD written = 0;
        WriteFile(log, line, static_cast<DWORD>(length), &written, NULL);
        CloseHandle(log);
    }

'''


def harden(root: Path) -> None:
    source = Path(root).resolve() / "xr_3da" / "xrRender_VK" / "vk_bootstrap.cpp"
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")

    marker = "    bool xr_vk_read_shader_sidecar(const char* stage, u64 identity, xr_vector<u8>& bytes)\n"
    if "void xr_vk_log_missing_shader_sidecar" not in text:
        if marker not in text:
            raise RuntimeError("missing-sidecar diagnostics: shader sidecar reader marker missing")
        text = text.replace(marker, HELPERS + marker, 1)

    old = '''        xr_vector<u8> vertex_spirv;
        xr_vector<u8> pixel_spirv;
        if (!xr_vk_read_shader_sidecar("vs", key.vertex_shader_identity, vertex_spirv) ||
            !xr_vk_read_shader_sidecar("ps", key.pixel_shader_identity, pixel_spirv))
            return VK_NULL_HANDLE;
'''
    new = '''        xr_vector<u8> vertex_spirv;
        xr_vector<u8> pixel_spirv;
        const bool vertex_sidecar_loaded = xr_vk_read_shader_sidecar("vs", key.vertex_shader_identity, vertex_spirv);
        const bool pixel_sidecar_loaded = xr_vk_read_shader_sidecar("ps", key.pixel_shader_identity, pixel_spirv);
        if (!vertex_sidecar_loaded || !pixel_sidecar_loaded)
        {
            if (!vertex_sidecar_loaded)
                xr_vk_log_missing_shader_sidecar("vs", key.vertex_shader_identity);
            if (!pixel_sidecar_loaded)
                xr_vk_log_missing_shader_sidecar("ps", key.pixel_shader_identity);
            return VK_NULL_HANDLE;
        }
'''
    if "vertex_sidecar_loaded" not in text:
        if old not in text:
            raise RuntimeError("missing-sidecar diagnostics: materializer sidecar load block missing")
        text = text.replace(old, new, 1)

    source.write_text(text, encoding="utf-8")
    final = source.read_text(encoding="utf-8")
    required = (
        "struct xr_vk_missing_sidecar_record",
        "g_missing_sidecars",
        "void xr_vk_log_missing_shader_sidecar",
        'CreateFileA("vulkan_missing_sidecars.log", FILE_APPEND_DATA',
        '"%s_%016I64x.spv\\r\\n"',
        "const bool vertex_sidecar_loaded",
        "const bool pixel_sidecar_loaded",
        'xr_vk_log_missing_shader_sidecar("vs", key.vertex_shader_identity);',
        'xr_vk_log_missing_shader_sidecar("ps", key.pixel_shader_identity);',
    )
    for token in required:
        if token not in final:
            raise RuntimeError(f"missing-sidecar diagnostics validation failed: missing {token}")
    print("[vulkan-sidecar-diagnostics] deduplicated missing VS/PS identities logged to vulkan_missing_sidecars.log")


def main() -> int:
    parser = argparse.ArgumentParser(description="Log missing SPIR-V sidecar identities during RC6 Vulkan fallback.")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
