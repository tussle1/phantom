# Phantom

A local browser workspace and Python companion for Windows, with a synthetic visual preview. No third-party runtime dependencies. Python 3.11 or newer.

**This is a foundation, not the complete requested CS2 modification suite. There is no injection, game memory access, live ESP, automated aiming/firing, or modification of CS2.** Gameplay settings are stored preferences only. The UI labels these boundaries explicitly.

## Run on Windows

Double-click `start-windows.cmd`, or run:

```powershell
py -3 companion.py
```

Open **http://127.0.0.1:8765**. Keep the terminal running; Ctrl+C stops the companion. `cs2.exe` detection uses Windows Tool Help process enumeration, not injection. A detected PID does not mean a telemetry connection. The Windows API code must still be verified on Windows; development tests run on Linux.

## Implemented behavior

- A responsive browser dashboard with a synthetic scene and radar, skeleton/health/armor preview rendering, visibility colors, teammate filtering, range filtering, color palettes, and sample indicators.
- Windows process detection every two seconds with snapshot handles closed after use.
- Validated settings; named config save/load/delete; atomic file replacement. Config names cannot escape the config directory. Preferences take effect in the preview or remain explicitly labeled stored preferences.
- Key/mouse binding capture **inside the browser**, not global hooks.
- Same-origin API writes, random per-run write token, host validation, revision checks, bounded request bodies, and no CORS permissions.

Settings are kept in memory until saved to a named config. Restarting restores defaults; load a saved config to restore it. Named configurations default to `%LOCALAPPDATA%\Phantom\configs` on Windows and `~/.config/Phantom/configs` elsewhere. Choose another directory using `--config-dir PATH`.

## Not implemented

No live game-state provider or map parser exists. All scene coordinates, skeletons, occlusion flags, sounds, bomb timers, and spectator names are fabricated. None of the hardlock/silent/humanized aim, bone fallback, recoil, trigger, prediction, bunny hop, grenade helper, camera changes, no-spread, no-flash, no-smoke, or third-person preferences interact with the game. There is no SmoothDamp implementation or sound-ESP code from FliXxCZ. No anti-cheat compatibility or server-side behavior is claimed.

The browser cannot obtain these capabilities on its own. Implementing live integration would require a separate, version-specific native adapter; this repository does not contain one.

## Preview on other platforms

```sh
python companion.py --demo
```

Open http://127.0.0.1:8765. Process detection is Windows-only. Demo mode does not invent a detected game process.

For a proxied development preview:

```sh
python companion.py --demo --host 0.0.0.0 --port 8765 \
  --public-origin https://8765-YOUR-SANDBOX.e2b.app
```

Use an exact origin without a trailing slash. Non-loopback binds are rejected outside demo mode. Demo servers are for trusted development environments: anyone who can reach the allowed origin can obtain a session token and edit the demo workspace. Do not expose the companion to an untrusted network. Other local programs running as your OS user are outside this API's security boundary.

## Tests

```sh
python -m unittest discover -s tests -v
node --check web/app.js
```

The standard-library suite exercises schema validation, hostile config names, atomic persistence and round trips, API authentication/origins/host checks, stale updates, size limits, missing/corrupt configs, and static serving. Windows process detection is not exercised by Linux tests.
