# Phantom C++ internal-foundation DLL

This directory builds `phantom-internal-foundation.dll` (or the platform shared library used by tests) and exposes a small C ABI.

**Status: experimental and not live-validated against CS2.** The DLL now contains a build-specific, opt-in in-process bomb reader and transparent Windows overlay. Loading the DLL alone does nothing: a host must explicitly call `phantom_runtime_start_bomb_overlay()`. Reads fail closed if `client.dll`, mapped fields, or timing data are unavailable. The implementation uses a pinned reference profile and fabricated-memory tests; those tests are not proof that current live-game offsets, injection, or rendering work.

Implemented and tested:

- Pure bomb-timer evaluation with stale-data rejection and explicit ticking, defusing, elapsed, and defused phases.
- C++ entity/bomb decoding against a sparse fabricated-memory fixture.
- Windows-only runtime exports in `phantom/runtime.h` for direct in-process bomb capture and an opt-in Poppins timer overlay.
- A capacity-bounded cosmetic-preference store for weapon definition, paint kit, seed, wear, and optional StatTrak.
- A host-driven cosmetic controller that records baselines, applies values through an adapter, refreshes, and restores; tests use a fabricated adapter. It is not connected to CS2.
- Windows CI build, CTest coverage, and DLL load/unload/export smoke testing.

Not implemented or validated:

- DLL injection or any anti-cheat bypass.
- A working local cosmetic override/refresh path. `phantom_apply_cosmetics()` still returns `PHANTOM_NOT_INTEGRATED`; preferences are not written, networked, rendered, or applied.
- Live CS2 validation of module offsets, field offsets, bomb-site mapping, overlay behavior, or lifecycle safety.
- Inventory ownership changes or cosmetics visible to other players.

The cosmetic controller in `phantom/cosmetics.h` requires a host-supplied adapter that resolves serial-bearing local weapon handles, verifies ownership on every operation, writes values, and refreshes materials on the game thread. It has no C ABI, no built-in adapter, no UI and does not make `phantom_apply_cosmetics()` operational.

No anti-cheat compatibility or account safety is claimed. Treat the runtime adapter as unverified until it is tested in an isolated/offline environment against the exact target build.

## Build

```powershell
cmake -S cpp -B build-cpp -A x64
cmake --build build-cpp --config Release
ctest --test-dir build-cpp -C Release --output-on-failure
```

Windows CI builds the x64 DLL, runs the unit and load/unload smoke tests, and places the DLL, public headers, and this status document in the downloadable package. See the root README for the main application scope.
