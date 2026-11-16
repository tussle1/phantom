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

PHANTOM_API uint32_t PHANTOM_CALL phantom_runtime_is_available(void);
/* Direct in-process read + pure timing evaluation. Never fabricates a timer. */
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_capture_bomb(PhantomBombTiming* out);
/* Host must explicitly call this after the DLL has been loaded into the game.
   Loading the DLL alone never draws or reads game memory. */
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_start_bomb_overlay(const PhantomBombOverlayOptions* options);
PHANTOM_API int32_t PHANTOM_CALL phantom_runtime_stop_bomb_overlay(void);

#ifdef __cplusplus
}
#endif
