#pragma once
#include <stdint.h>

#if defined(_WIN32)
# if defined(PHANTOM_BUILD_DLL)
#  define PHANTOM_API __declspec(dllexport)
# else
#  define PHANTOM_API __declspec(dllimport)
# endif
# define PHANTOM_CALL __cdecl
#else
# define PHANTOM_API __attribute__((visibility("default")))
# define PHANTOM_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum PhantomResult {
    PHANTOM_OK = 0, PHANTOM_INVALID_ARGUMENT = 1, PHANTOM_STALE_DATA = 2,
    PHANTOM_NOT_INTEGRATED = 3, PHANTOM_NOT_FOUND = 4,
    PHANTOM_CAPACITY_REACHED = 5, PHANTOM_INTERNAL_ERROR = 6
};
enum PhantomBombPhase {
    PHANTOM_BOMB_UNAVAILABLE = 0, PHANTOM_BOMB_INACTIVE = 1,
    PHANTOM_BOMB_TICKING = 2, PHANTOM_BOMB_DEFUSING = 3,
    PHANTOM_BOMB_DEFUSED = 4, PHANTOM_BOMB_EXPIRED = 5
};
enum PhantomDefuseEstimate {
    PHANTOM_DEFUSE_UNKNOWN = 0, PHANTOM_DEFUSE_EXPECTED_BEFORE = 1,
    PHANTOM_DEFUSE_EXPECTED_AFTER = 2
};

typedef struct PhantomIntegrationStatus {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t game_adapter_ready;
    uint32_t live_bomb_timer_ready;
    uint32_t cosmetic_changes_ready;
    char reason[160];
} PhantomIntegrationStatus;

/* Timestamps must share the same game-clock timebase. This pure evaluator accepts
   host snapshots; runtime.h separately exposes an opt-in Windows capture adapter. */
typedef struct PhantomBombSnapshot {
    uint32_t struct_size;
    uint32_t valid;
    uint32_t planted;
    uint32_t defused;
    uint32_t defusing;
    uint32_t site; /* 0 unknown, 1 A, 2 B */
    double game_time;
    double detonation_time;
    double defuse_end_time;
    double observation_age;
} PhantomBombSnapshot;

typedef struct PhantomBombTiming {
    uint32_t struct_size;
    uint32_t phase;
    uint32_t site;
    uint32_t defuse_estimate;
    double explosion_remaining;
    double defuse_remaining;
} PhantomBombTiming;

/* Desired cosmetic data only. IDs are not looked up against a game catalog.
   Storing a preference never alters inventory, rendering or game memory. */
typedef struct PhantomCosmeticPreference {
    uint32_t struct_size;
    uint32_t weapon_definition;
    uint32_t paint_kit;
    uint32_t seed;
    float wear;
    int32_t stattrak; /* -1 means disabled */
} PhantomCosmeticPreference;

PHANTOM_API uint32_t PHANTOM_CALL phantom_abi_version(void);
PHANTOM_API int32_t PHANTOM_CALL phantom_get_integration_status(PhantomIntegrationStatus* out);
PHANTOM_API int32_t PHANTOM_CALL phantom_evaluate_bomb(const PhantomBombSnapshot* snapshot, PhantomBombTiming* out);
PHANTOM_API int32_t PHANTOM_CALL phantom_set_cosmetic_preference(const PhantomCosmeticPreference* preference);
PHANTOM_API int32_t PHANTOM_CALL phantom_get_cosmetic_preference(uint32_t weapon_definition, PhantomCosmeticPreference* out);
PHANTOM_API int32_t PHANTOM_CALL phantom_remove_cosmetic_preference(uint32_t weapon_definition);
PHANTOM_API int32_t PHANTOM_CALL phantom_list_cosmetic_preferences(PhantomCosmeticPreference* out, uint32_t capacity, uint32_t* out_count);
/* Optional local-only nametag (<= 32 printable ASCII chars) and mesh group
   override (0 = auto, 1 = modern, 2 = legacy) attached to a stored weapon preference. */
PHANTOM_API int32_t PHANTOM_CALL phantom_set_cosmetic_custom_name(uint32_t weapon_definition, const char* custom_name);
PHANTOM_API int32_t PHANTOM_CALL phantom_get_cosmetic_custom_name(uint32_t weapon_definition, char* out, uint32_t out_capacity);
PHANTOM_API int32_t PHANTOM_CALL phantom_set_cosmetic_mesh_group(uint32_t weapon_definition, uint64_t mesh_group_mask);
PHANTOM_API int32_t PHANTOM_CALL phantom_get_cosmetic_mesh_group(uint32_t weapon_definition, uint64_t* out_mask);
PHANTOM_API int32_t PHANTOM_CALL phantom_clear_cosmetic_preferences(void);
/* Applies/restores local cosmetic preferences when loaded in-process with client.dll.
   Returns PHANTOM_NOT_INTEGRATED outside CS2. Local-only: never alters inventory ownership. */
PHANTOM_API int32_t PHANTOM_CALL phantom_apply_cosmetics(void);
PHANTOM_API int32_t PHANTOM_CALL phantom_restore_cosmetics(void);

#ifdef __cplusplus
}
#endif
