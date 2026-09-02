from __future__ import annotations

import argparse
from pathlib import Path


DLLMAIN_OLD = '''\tcase DLL_PROCESS_ATTACH: {\n\t\t// register console commands\n\t\tCCC_RegisterCommands();\n\t\t// keyboard binding\n\t\tCCC_RegisterInput();\n#ifdef DEBUG\n\t\tg_profiler = xr_new<CProfiler>();\n#endif\n\t\tbreak;\n\t}\n'''

DLLMAIN_NEW = '''\tcase DLL_PROCESS_ATTACH: {\n\t\t// Keep DllMain loader-lock safe. EngineAPI calls xrFactory_Initialize\n\t\t// immediately after LoadLibrary returns.\n\t\tDisableThreadLibraryCalls((HMODULE)hModule);\n\t\tbreak;\n\t}\n'''

INIT_EXPORT = '''\nextern "C" DLL_API BOOL __cdecl xrFactory_Initialize()\n{\n\tstatic bool initialized = false;\n\tif (initialized)\n\t\treturn TRUE;\n\n\t// Console registration reads configuration/registry data and allocates memory.\n\t// It must not execute from DllMain while the Windows loader lock is held.\n\tCCC_RegisterCommands();\n\tCCC_RegisterInput();\n#ifdef DEBUG\n\tg_profiler = xr_new<CProfiler>();\n#endif\n\tinitialized = true;\n\treturn TRUE;\n}\n'''

ENGINE_MARKER = '''\t\tpDestroy = (Factory_Destroy*)GetProcAddress(hGame, "xrFactory_Destroy");\n\t\tR_ASSERT(pDestroy);\n'''

ENGINE_REPLACEMENT = ENGINE_MARKER + '''\t\ttypedef BOOL (__cdecl *Factory_Initialize)();\n\t\tFactory_Initialize initialize =\n\t\t\treinterpret_cast<Factory_Initialize>(GetProcAddress(hGame, "xrFactory_Initialize"));\n\t\tR_ASSERT2(initialize, "Cannot obtain xrFactory_Initialize from xrGame.dll");\n\t\tR_ASSERT2(initialize && initialize(), "xrGame post-load initialization failed");\n'''

READ_STR_OLD = '''void ReadRegistry_StrValue(LPCSTR rKeyName, char* value)\n{\n\tReadRegistryValue(rKeyName, REG_SZ, value);\n}\n'''

READ_STR_NEW = '''void ReadRegistry_StrValue(LPCSTR rKeyName, char* value)\n{\n\tif (!value)\n\t\treturn;\n\tvalue[0] = '\\0';\n\tReadRegistryValue(rKeyName, REG_SZ, value);\n}\n'''

READ_DWORD_OLD = '''void ReadRegistry_DWValue(LPCSTR rKeyName, DWORD& value)\n{\n\tReadRegistryValue(rKeyName, REG_DWORD, &value);\n}\n'''

READ_DWORD_NEW = '''void ReadRegistry_DWValue(LPCSTR rKeyName, DWORD& value)\n{\n\tvalue = 0;\n\tReadRegistryValue(rKeyName, REG_DWORD, &value);\n}\n'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one marker, found {count}")
    return text.replace(old, new, 1)


def harden(root: Path) -> None:
    root = root.resolve()
    game = root / "xr_3da" / "xrGame" / "xrGame.cpp"
    engine = root / "xr_3da" / "EngineAPI.cpp"
    registry = root / "xr_3da" / "xrGame" / "RegistryFuncs.cpp"
    for path in (game, engine, registry):
        if not path.is_file():
            raise FileNotFoundError(path)

    game_text = game.read_text(encoding="utf-8")
    if 'extern "C" DLL_API BOOL __cdecl xrFactory_Initialize()' not in game_text:
        marker = "extern void CCC_RegisterCommands();\n"
        if marker not in game_text:
            raise RuntimeError("x64 game startup: command-registration declaration missing")
        game_text = game_text.replace(marker, marker + INIT_EXPORT, 1)
    game_text = replace_once(game_text, DLLMAIN_OLD, DLLMAIN_NEW, "x64 game startup DllMain")
    game.write_text(game_text, encoding="utf-8")

    engine_text = engine.read_text(encoding="utf-8")
    engine_text = replace_once(engine_text, ENGINE_MARKER, ENGINE_REPLACEMENT, "x64 game startup EngineAPI")
    engine.write_text(engine_text, encoding="utf-8")

    registry_text = registry.read_text(encoding="utf-8")
    registry_text = replace_once(registry_text, READ_STR_OLD, READ_STR_NEW, "registry string default")
    registry_text = replace_once(registry_text, READ_DWORD_OLD, READ_DWORD_NEW, "registry DWORD default")
    registry.write_text(registry_text, encoding="utf-8")

    validate(root)
    print("[x64-startup] xrGame command/input registration moved out of DllMain; missing registry values now have deterministic defaults")


def validate(root: Path) -> None:
    root = root.resolve()
    game = (root / "xr_3da" / "xrGame" / "xrGame.cpp").read_text(encoding="utf-8", errors="ignore")
    engine = (root / "xr_3da" / "EngineAPI.cpp").read_text(encoding="utf-8", errors="ignore")
    registry = (root / "xr_3da" / "xrGame" / "RegistryFuncs.cpp").read_text(encoding="utf-8", errors="ignore")

    attach_start = game.find("case DLL_PROCESS_ATTACH:")
    attach_end = game.find("break;", attach_start)
    if min(attach_start, attach_end) < 0:
        raise RuntimeError("x64 game startup validation: DLL_PROCESS_ATTACH block missing")
    attach = game[attach_start:attach_end]
    for forbidden in ("CCC_RegisterCommands()", "CCC_RegisterInput()", "xr_new<CProfiler>()"):
        if forbidden in attach:
            raise RuntimeError(f"x64 game startup validation: loader-lock side effect remains: {forbidden}")

    required_game = (
        'extern "C" DLL_API BOOL __cdecl xrFactory_Initialize()',
        "CCC_RegisterCommands();",
        "CCC_RegisterInput();",
        "DisableThreadLibraryCalls((HMODULE)hModule);",
    )
    required_engine = (
        'GetProcAddress(hGame, "xrFactory_Initialize")',
        "initialize && initialize()",
    )
    required_registry = ("value[0] = '\\0';", "value = 0;")
    for token in required_game:
        if token not in game:
            raise RuntimeError(f"x64 game startup validation: xrGame token missing: {token}")
    for token in required_engine:
        if token not in engine:
            raise RuntimeError(f"x64 game startup validation: EngineAPI token missing: {token}")
    for token in required_registry:
        if token not in registry:
            raise RuntimeError(f"x64 game startup validation: registry token missing: {token}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Move xrGame initialization out of DllMain and harden missing registry defaults.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        validate(Path(args.root))
    else:
        harden(Path(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
