"""Package an already built Windows x64 executable; this does not cross-compile."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native.config import Config
from native.version import __version__
from native.presets import PRESETS, preset_document, preset_filename
from native.schema import load_profile

RUN = '''@echo off\r
cd /d "%~dp0"\r
"%~dp0phantom-native.exe" --profile "%~dp0offset-profile.json" %*\r
set "RESULT=%ERRORLEVEL%"\r
if not "%RESULT%"=="0" pause\r
exit /b %RESULT%\r
'''
INSTRUCTIONS = 'PHANTOM v'+__version__+''' - WINDOWS X64

1. Extract the entire ZIP into a folder. Do not run from inside the ZIP.
2. Double-click run.cmd. The Phantom startup console and native control panel open together. No Python is required.
3. Click Start runtime in the panel when you want to attach. The console only reports attachment after cs2.exe is actually attached; Stop detaches.
4. Right Shift hides/reopens the menu. The worker pauses while the menu is open.
5. Use borderless/windowed CS2. End stops the runtime; the panel stays open.
6. Rebind Menu toggle in Input; save in Configs to persist it.

Poppins is bundled in the EXE; no system font installation is required.

Presets: Configs > Built-in presets > select > Apply preset > confirm.
Some practice presets ENABLE hold-key aim or trigger; read the description.
Runtime must be stopped. Save a named config to persist applied settings.
The presets/ directory also contains full default-binding JSON configs. To import
one manually, copy it into your native configs folder, then load it in Configs.
Imported JSON uses default keys/bones/calibration; GUI Apply preserves yours.
No preset is live-tested, ban-safe, or an anti-cheat compatibility claim.

Included:
  phantom-native.exe  - Windows x64 executable
  offset-profile.json - Pinned reference profile (build page 26598758)
  run.cmd             - Launches the EXE with the included profile
  CONFIG.example.json - Reference only; runtime creates a separate default config
  README.md           - Full implementation status and limitations
  BUILD.json          - Source revision and executable SHA-256
  phantom-cpp/        - Tested C++ foundation DLL and headers (not live hooks)

Aim and trigger are disabled in new configs. F6 ESP, F7 aim, F8 trigger,
F9 reload config, F10 save config. Right mouse holds aim; left Alt holds
trigger when those features are enabled.

Native configs: %LOCALAPPDATA%\\PhantomNative\\configs
Normal operation does not download offsets. To explicitly replace the included
profile with a newly pinned GitHub dump, open a terminal in this folder and run:
  phantom-native.exe --update-offsets --profile offset-profile.json

The bundled offsets are a reference, not proof of current game compatibility.
The build checks packaging, API imports, unit tests, CLI tools and offscreen GUI rendering.
phantom-cpp contains an x64 C++ foundation tested WITHOUT CS2. It has no
injection, game hooks, live bomb reads, rendering, or cosmetic application.
It does NOT provide working skins or bomb timers by itself. It does NOT test actual CS2 behavior, overlay rendering, live memory offsets,
or whether the game accepts synthetic input. This is not the full requested
feature suite. See README.md for the exact implementation scope.
Game memory reads/input automation can result in account bans. No anti-cheat
compatibility is claimed.
'''


def check_pe(executable):
    with Path(executable).open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError('Expected a built Windows executable, not source or a renamed file.')
        offset = struct.unpack_from('<I', header, 0x3C)[0]
        size = Path(executable).stat().st_size
        if not 64 <= offset <= min(size-26, 16*1024*1024):
            raise ValueError('Invalid PE header offset.')
        stream.seek(offset)
        pe = stream.read(26)
        if pe[:4] != b'PE\0\0' or struct.unpack_from('<H', pe, 4)[0] != 0x8664 or struct.unpack_from('<H', pe, 24)[0] != 0x20B:
            raise ValueError('Expected an AMD64 PE32+ executable.')


def package(executable, output, revision, foundation_dll=None):
    executable, output = Path(executable), Path(output)
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('An exact source commit SHA is required for BUILD.json.')
    check_pe(executable)
    dll = None
    if foundation_dll is not None:
        dll = Path(foundation_dll)
        if not dll.is_file():
            raise ValueError(f'C++ foundation DLL does not exist: {dll}')
        check_pe(dll)
    profile = ROOT/'native/profiles/reference-26598758.json'
    load_profile(profile)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    dll_digest = None
    if dll is not None:
        dll_digest = hashlib.sha256(dll.read_bytes()).hexdigest()
    manifest = {'app_version': __version__, 'source_commit': revision, 'platform': 'windows-x64',
                'executable_sha256': digest, 'game_behavior_verified': False,
                'cpp_foundation_included': dll is not None,
                'cpp_foundation_sha256': dll_digest}
    output.parent.mkdir(parents=True, exist_ok=True)
    # All names are fixed, relative paths. No checkout, secrets, or caches enter the ZIP.
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(executable, 'phantom-native.exe')
        archive.write(profile, 'offset-profile.json')
        archive.write(ROOT/'README.md', 'README.md')
        archive.write(ROOT/'native/assets/fonts/OFL.txt', 'FONT-LICENSE.txt')
        archive.writestr('run.cmd', RUN)
        archive.writestr('RUN-ME.txt', INSTRUCTIONS)
        archive.writestr('CONFIG.example.json', json.dumps({'version': 1, 'settings': asdict(Config())}, indent=2))
        archive.writestr('BUILD.json', json.dumps(manifest, indent=2))
        if dll is not None:
            archive.write(dll, 'phantom-cpp/phantom-internal-foundation.dll')
            archive.write(ROOT/'cpp/README.md', 'phantom-cpp/README.md')
            archive.write(ROOT/'cpp/include/phantom/api.h', 'phantom-cpp/include/phantom/api.h')
            archive.write(ROOT/'cpp/include/phantom/runtime.h', 'phantom-cpp/include/phantom/runtime.h')
        for name in PRESETS:
            archive.writestr('presets/'+preset_filename(name), json.dumps(preset_document(name), indent=2))
    print(f'Packaged {output} ({output.stat().st_size:,} bytes); EXE SHA-256 {digest}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--foundation-dll', type=Path)
    args = parser.parse_args()
    package(args.exe, args.output, args.revision, args.foundation_dll)


if __name__ == '__main__':
    main()
