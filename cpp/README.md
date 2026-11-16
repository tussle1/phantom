# Phantom C++ internal-foundation DLL

This directory builds `phantom-internal-foundation.dll` (or the platform shared library used by tests) and exposes a small C ABI.

**Status: experimental and not live-validated against CS2.** The DLL contains build-specific, opt-in in-process bomb-timer and local skin-changer runtime adapters. Loading the DLL alone does nothing: a host must explicitly call `phantom_runtime_start_bomb_overlay()`, `phantom_runtime_apply_skins()`, or `phantom_runtime_start_skin_watcher()`. Operations fail closed if `client.dll`, mapped fields, serial-bearing handles, or local ownership checks fail. The implementation uses the pinned `a2x/cs2-dumper` reference profile and fabricated-memory tests; those tests are not proof that current live-game offsets, injection, or rendering work.

Implemented and tested:

- Pure bomb-timer evaluation with stale-data rejection and explicit ticking, defusing, elapsed, and defused phases.
- C++ entity/bomb decoding against a sparse fabricated-memory fixture.
- Windows-only runtime exports in `phantom/runtime.h` for direct in-process bomb capture and an opt-in Poppins timer overlay.
- A capacity-bounded (32-weapon) cosmetic preference store in `phantom/api.h` for weapon definition, paint kit, seed, wear, optional StatTrak, optional custom local nametag, and model mesh group (`auto` / `modern` / `legacy`).
- `phantom::CosmeticController` and `phantom::MemoryCosmeticAdapter` in `phantom/cosmetics.h`, resolving local weapons from `CPlayer_WeaponServices`, verifying full 32-bit serial-bearing handles and local pawn ownership on every read/write/refresh, recording baselines, updating fallback skin attributes / `m_iItemIDHigh` / `m_iAccountID` / `m_iEntityQuality` / `m_szCustomName` / `m_MeshGroupMask` / `m_nCustomEconReloadEventId`, rolling back on failure, and restoring exact original baselines on removal or shutdown.
- Strict `.skin-loadout.json` parsing (`phantom_runtime_load_skin_file`) compatible with the native Python panel's **Skins** tab and `phantom.py --export-skins`.
- Opt-in local skin runtime exports in `phantom/runtime.h` (`phantom_runtime_apply_skins`, `phantom_runtime_restore_skins`, `phantom_runtime_start_skin_watcher`, `phantom_runtime_stop_skin_watcher`) plus `phantom_apply_cosmetics()` / `phantom_restore_cosmetics()` (returning `PHANTOM_NOT_INTEGRATED` outside CS2).
- Windows CI build, CTest coverage, and DLL load/unload/export smoke testing.

Not implemented or validated:

- DLL injection or any anti-cheat bypass.
- Live CS2 validation of module offsets, field offsets, bomb-site mapping, weapon fallback/mesh refresh behavior, overlay behavior, or lifecycle safety.
- Inventory ownership changes or cosmetics visible to other players.

No anti-cheat compatibility or account safety is claimed. Treat the runtime adapters as unverified until tested in an isolated/offline environment against the exact target build.

## Build

```powershell
cmake -S cpp -B build-cpp -A x64
cmake --build build-cpp --config Release
ctest --test-dir build-cpp -C Release --output-on-failure
```

Windows CI builds the x64 DLL, runs the unit and load/unload smoke tests, and places the DLL, public headers, and this status document in the downloadable package. See the root README for the main application scope.
