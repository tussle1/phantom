# Phantom native

Standalone **64-bit Windows** external runtime using `ReadProcessMemory`, a click-through GDI overlay, and foreground-gated `SendInput`. No browser, web server, injected DLL, kernel driver, or game-memory writes are used by `phantom.py`.

**This is native implementation code, not a verified complete cheat suite. The Windows build pipeline passes unit tests, Win32 import/ABI checks, and packaged CLI smoke tests. The runtime has not been tested against CS2; passing these checks does not establish live compatibility.** Game updates can invalidate the profile, entity layout, and bone indices independently. Reading or automating a game can result in account bans; no anti-cheat compatibility is claimed.

## Start

Install **64-bit Python 3.11+**. The control panel uses Qt Widgets (PySide6 Essentials); the optional `--headless` runtime remains standard-library only.

```powershell
py -3 -m pip install -r requirements-gui.txt

# Explicit setup: fetch a consistent, commit-pinned a2x/cs2-dumper profile.
py -3 phantom.py --update-offsets

# Open the native control panel. Click Start runtime to attach.
py -3 phantom.py
```

After setup, `start-windows.cmd` opens the same native control panel on Windows. Use `--headless` to run directly without a panel. Use borderless/windowed CS2: the external overlay does not support exclusive fullscreen. After Start is clicked, hide the menu with **Right Shift** to let its separate worker wait for `cs2.exe`; memory access failures or invalid frames suppress drawing/input instead of substituting sample data. Aim and trigger are off in newly created configs.

There is no synthetic fallback in the native runtime. The legacy preview remains in `companion.py`/`web/`, but is not imported or launched by `phantom.py`.

### Supplied offset reference

The supplied [CheatOffsets page](https://www.cheatoffsets.com/g/cs2) listed build **26598758**. A reference profile is included at `native/profiles/reference-26598758.json`. The entity list, local controller, local pawn, view angles, and view matrix module values match that page. The complete required schema/sensitivity fields are extracted from **one** pinned [a2x/cs2-dumper](https://github.com/a2x/cs2-dumper) commit, recorded in the profile; unrelated dumps are not silently mixed.

To explicitly use that reference instead of the downloaded profile:

```powershell
py -3 phantom.py --profile native/profiles/reference-26598758.json
```

The filename identifies the reference page, not a verified compatibility assertion. The runtime does not compare the installed game build to a Steam build ID. It validates structure, pointer reads, local-controller linkage, matrix/vector ranges and scalar ranges; these checks cannot prove every offset correct.

The updater makes three HTTPS requests to GitHub only when explicitly invoked. Normal operation is local/offline. To pin an exact dump revision or import your own files:

```powershell
py -3 phantom.py --update-offsets --ref EXACT_40_CHARACTER_COMMIT_SHA
py -3 phantom.py --import-dumps C:\path\to\dump\output --ref EXACT_40_CHARACTER_COMMIT_SHA
py -3 phantom.py --check-profile
```

`--check-profile` checks file structure only, not the running game. Missing schema fields reject the profile. There is no signature scanner or guessed substitute offset.

## Native control panel

The panel recreates the supplied reference's compact dark-purple layout, pink pill toggles,
outlined sliders, faceted purple tabs, banner, collapsible **More / Less** section, and
cyan/pink action buttons. It uses native Qt Widgets, not HTML, a browser, or WebEngine.
The banner is cropped from the user-supplied reference image; the controls and artwork
buttons are drawn by Qt. Labels and controls are adapted to the implemented CS2 settings,
not the rhythm-game autoplay controls in the reference.

- **Visuals:** skeleton, health/armor bars, teammates, radar, spectators, range.
- **Aim:** mode, priority bone, smoothing, angular FOV, speed and linear prediction.
- **Input:** movement preference and real key/mouse binding capture; Escape cancels.
- **Configs:** validated named save/load and an explicit offset-profile file picker.

Changes are sent to the running native worker over bounded IPC, without blocking the UI.
**Start runtime** saves the active configuration and launches the worker; **Stop** signals
it to clean up its overlay and process handle. Closing the panel also stops its worker,
with a three-second watchdog for an unresponsive process. The panel itself never performs
memory reads or sends game input. Save in Configs keeps edits made while stopped.

The window can be previewed without Windows/game access if Qt and platform libraries are installed:

```sh
python phantom.py --gui --profile native/profiles/reference-26598758.json
QT_QPA_PLATFORM=offscreen python phantom.py --gui --screenshot-dir artifacts/ui --profile native/profiles/reference-26598758.json
```

### Font and menu key

The panel bundles **Poppins Regular** (SIL Open Font License 1.1), registered as
an application font before any UI text is painted. You do not need to install
Poppins. Both Qt widgets and custom-painted captions use the same bundled face;
reset, minimize and close icons are drawn as vectors rather than symbol glyphs.
The package validates required Latin/punctuation glyphs and includes `FONT-LICENSE.txt`.

**Right Shift** shows/hides the menu on Windows, even while the runtime is stopped,
the panel is hidden, or another application has focus. Holding the key does not
repeatedly toggle it. Minimized panels are restored. This requires the panel
process to remain running; `--headless` has no menu. The menu stays on top when open.

To customize it, open **Input → Menu toggle**, click the binding, press the new key
or mouse button, then use **Configs → Save named config**. Escape cancels capture.
Left and right modifiers are distinguished, and conflicting generic/side-specific
modifier bindings are rejected. Capture and modal dialogs suppress menu toggling.
Old version-1 configs without a menu key are upgraded in memory without changing
existing bindings: Right Shift is preferred, then an unused fallback if necessary.
The active binding is always displayed beside More/Less and in Input.

Opening the menu pauses the worker's overlay and game input. Hide/minimize it to
resume, still subject to the foreground-game checks. Stop and emergency exit remain
available while paused. Closing the panel still stops its worker cleanly.

The second command above captures the actual control panel, not a game/overlay screenshot.
Starting the native worker still requires Windows. Opening the panel does not attach to CS2.

## Native implementation scope

| Part | What the code does | Important boundary |
|---|---|---|
| ESP | Decode player controllers/pawns and draw skeletons, health/armor bars, names, distance, team filtering | GDI overlay, not in-game GlowV2. Bones are omitted on failed spatial checks. |
| Colors | Read the local controller's bit in the entity spotted mask | **Not** a map raycast or per-bone visibility check; a spotted actor can still be behind cover. |
| Aim | Hold-key hardlock or critically damped smoothing, selected real bone, angular FOV filter, enemy-only selection | Disabled by default. `SendInput` mouse counts, not silent aim. Hardlock still has a speed cap. No randomizers. |
| Prediction | Optional constant-velocity look-ahead in milliseconds | Not a latency/ballistic/server-tick model. |
| Trigger | Crosshair entity lookup, enemy/spotted checks, stable-target delay and repeated-shot cooldown | Disabled by default. No weapon readiness, ammo or fire-rate model. |
| Bunny hop | Optional grounded transition → Space press/release | Disabled by default. No server compatibility guarantee. |
| Radar | Player-centered circular radar rotated by local yaw | No map texture, parsing, or height-layer model. |
| Spectators | Resolve observer services/target handles back to the local pawn | Only actors resolvable from the sampled entity list. |
| Configs/hotkeys | Named atomic JSON configs; configurable Windows virtual-key bindings; live reload/save | Native Qt control panel with live settings; separate from legacy browser configs. |

**Not implemented:** silent aim, map parsing, per-bone visible fallback, anti-recoil, in-game GlowV2, sound ESP, bomb/defuse countdowns, grenade lineups, POV changes, no-spread, no-flash, no-smoke, third person, bullet tracers, hitmarkers, and an in-game visual-layout/bone editor. The panel edits implemented ESP preferences. Unsupported settings are rejected rather than offered as nonfunctional switches. No FliXxCZ code is included or implied.

## Controls and configurations

Runtime bindings apply while CS2 is foreground, except **End**, which exits the worker globally. The panel's menu key works independently of the worker:

| Binding | Action |
|---|---|
| Right Shift | Show/hide menu (rebindable in Input) |
| F5 | Radar on/off |
| F6 | ESP on/off |
| F7 | Toggle aim off / the configured mode (smooth if no mode selected) |
| Hold right mouse | Aim activation when aim is enabled |
| F8 | Trigger on/off |
| Hold left Alt | Trigger activation when enabled |
| Hold Space | Bunny hop when enabled in config |
| F9 | Reload the selected named config |
| F10 | Save current settings to that config |
| End | Exit |

Config location: `%LOCALAPPDATA%\PhantomNative\configs\NAME.json`. Profile: `%LOCALAPPDATA%\PhantomNative\offset-profile.json`.

```powershell
py -3 phantom.py --config practice --init-config
py -3 phantom.py --list-configs
py -3 phantom.py --config practice
```

Use the control panel, or edit a native JSON config in a text editor and press F9 while the runtime is active to reload. `aim` accepts `off`, `smooth`, or `hardlock`; `priority_bone` accepts `head`, `neck`, `chest`, or `pelvis`. `prediction_ms` defaults to zero. `keys` contains numeric Windows virtual-key codes. `bones` contains configurable model-specific bone indices. There is no automatic model skeleton discovery.

Mouse conversion assumes the configured `mouse_yaw` and `mouse_pitch` (both default 0.022), the memory-read sensitivity, and ordinary mouse input. Scoped sensitivity, game input settings, Windows mouse acceleration, or blocked synthetic input can make it inaccurate. Foreground is checked before sampling and again before emitting input; no global aim/fire loop is allowed to run against another foreground process.

Entity chunk parameters and candidate strides live in the profile's `layout` block. The stride must resolve the local controller's pawn handle to the actual local pawn **uniquely**. The skeleton-array pointer location and bone stride remain explicit build-dependent assumptions. Invalid/unreadable bones produce no skeleton or aim target.

## Optional executable

On Windows:

```powershell
py -3 -m pip install pyinstaller -r requirements-gui.txt
build-native.cmd
```

This produces the windowed GUI executable `dist\phantom-native.exe`. Run `phantom-native.exe --update-offsets` before normal launch. The GitHub Windows package pipeline also produces an executable with CLI smoke checks. Config/profile files stay outside the executable; live gameplay remains unverified.

## Tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q native phantom.py
```

The native suite exercises a sparse fabricated-memory fixture through entity traversal, stride calibration, schema decoding, skeleton rejection, local spotted-mask selection, target filters, SmoothDamp convergence, input math, prediction, trigger delay/cooldown, grounded transitions, strict configs, and CLI setup. These fixtures are test-only; they are not telemetry used by the runtime. Existing legacy API tests remain intact. Win32 imports/INPUT ABI are checked by Windows CI. Overlay rendering, actual memory reads, synthetic-input acceptance, process offsets, and gameplay behavior still require Windows/CS2 testing.

### Downloadable Windows ZIP

The **Windows package** GitHub Actions workflow builds on a Windows x64 runner,
checks Win32 imports/ABI, tests actual Qt controls, smoke-tests the executable and
captures its compact/expanded control panel, then uploads a
`phantom-windows-x64` artifact, downloadable as a ZIP with the files at its root (no nested ZIP).
The ZIP contains the EXE, pinned reference profile, a `run.cmd` launcher,
configuration example, instructions, actual control-panel screenshots, and a source revision/EXE SHA-256 manifest.
Extract the complete ZIP and double-click `run.cmd`; Python is not required.
A successful package build is not a live-game compatibility test.
