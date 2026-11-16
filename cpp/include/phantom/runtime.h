#pragma once
#include "phantom/api.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PhantomBombOverlayOptions {
    uint32_t struct_size;
    int32_t x;
    int32_t y;
    uint32_t width;
    uint32_t height;
    uint32_t font_height;
    uint32_t color_rgb; /* COLORREF-compatible: 0x00bbggrr */
} PhantomBombOverlayOptions;

typedef struct PhantomSkinApplyReport {
    uint32_t struct_size;
    uint32_t weapons_found;
    uint32_t weapons_applied;
    uint32_t weapons_restored;
    uint32_t weapons_failed;
} PhantomSkinApplyReport;

typedef struct PhantomSkinWatcherOptions {
    uint32_t struct_size;
    uint32_t poll_interval_ms; /* 50..5000 */
    uint32_t restore_on_stop;  /* 0 or 1 */
    char loadout_json_path[260]; /* Optional UTF-8 path to .skin-loadout.json */
} PhantomSkinWatcherOptions;

PHANTOM_API uint32_t PHANTOM_CALL phantom_runtime_is_available(void);
/* Direct in-process read + pure timing evaluation. Never fabricates a timer. */
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_capture_bomb(PhantomBombTiming* out);
/* Host must explicitly call this after the DLL has been loaded into the game.
   Loading the DLL alone never draws or reads game memory. */
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_start_bomb_overlay(const PhantomBombOverlayOptions* options);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_stop_bomb_overlay(void);

/* Experimental local-only skin changer runtime exports.
   Loading the DLL alone never reads, writes, or modifies weapons. */
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_load_skin_file(const char* path);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_apply_skins(PhantomSkinApplyReport* out);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_restore_skins(PhantomSkinApplyReport* out);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_start_skin_watcher(const PhantomSkinWatcherOptions* options);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_stop_skin_watcher(void);

#ifdef __cplusplus
}
#endif
