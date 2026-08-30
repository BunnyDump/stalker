from __future__ import annotations

import os
import tempfile
from pathlib import Path

from stage_rc6_release_gamedata import stage
from validate_rc6_release import parse_overlay_manifest


def write_fake_pe(path: Path) -> None:
    data = bytearray(0x100)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    path.write_bytes(data)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rc6-release-policy-") as temp:
        root = Path(temp)
        workspace = root / "workspace"
        source = root / "source"
        ready = root / "ready"
        (workspace / "release" / "gamedata-overlay" / "config").mkdir(parents=True)
        source.mkdir()
        (source / "gamedata" / "textures").mkdir(parents=True)
        (source / "gamedata" / "textures" / "MUST_NOT_SHIP.dds").write_bytes(b"junk")
        (workspace / "release" / "gamedata-overlay" / "config" / "changed.ltx").write_text("changed=true\n")
        (ready / "bin").mkdir(parents=True)

        for name in ("XR_3DA.exe", "xrCore.dll", "xrRender_VK.dll", "OpenAL32.dll"):
            write_fake_pe(ready / "bin" / name)

        vcpkg_bin = root / "xray-rc6-vcpkg" / "installed-openal" / "x64-windows" / "bin"
        vcpkg_bin.mkdir(parents=True)
        write_fake_pe(vcpkg_bin / "fmt.dll")
        old_temp = os.environ.get("TEMP")
        os.environ["TEMP"] = str(root)
        try:
            stage(workspace, source, ready)
        finally:
            if old_temp is None:
                os.environ.pop("TEMP", None)
            else:
                os.environ["TEMP"] = old_temp

        assert (ready / "bin" / "fmt.dll").is_file(), "fmt.dll runtime closure was not staged"
        assert (ready / "gamedata" / "config" / "changed.ltx").is_file()
        assert not (ready / "gamedata" / "textures" / "MUST_NOT_SHIP.dds").exists()
        declared = parse_overlay_manifest(ready / "GAMEDATA_OVERLAY_MANIFEST.txt")
        assert declared == {"config/changed.ltx"}, declared

    print("[release-policy-test] sparse gamedata and OpenAL/fmt runtime closure verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
