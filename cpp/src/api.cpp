#include "phantom/api.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <mutex>

namespace {
constexpr uint32_t abi = 1;
constexpr double stale_after = 0.5;
constexpr double estimate_margin = 0.1;
struct Store {
    std::mutex mutex;
    std::array<PhantomCosmeticPreference, 32> entries{};
};
Store& preferences() {
    // Construct only on an explicit API call, not under the DLL loader lock.
    static Store store;
    return store;
}
template<class T> bool sized(const T* value) {
    return value && value->struct_size == sizeof(T);
}
}

uint32_t PHANTOM_CALL phantom_abi_version(void) { return abi; }

int32_t PHANTOM_CALL phantom_get_integration_status(PhantomIntegrationStatus* out) {
    if (!sized(out)) return PHANTOM_INVALID_ARGUMENT;
    *out = {};
    out->struct_size = sizeof(*out);
    out->abi_version = abi;
    constexpr char reason[] = "Experimental bomb adapter is present but not live-validated; cosmetic refresh is not implemented.";
    static_assert(sizeof(reason) <= sizeof(out->reason));
    std::memcpy(out->reason, reason, sizeof(reason));
    return PHANTOM_OK;
}

int32_t PHANTOM_CALL phantom_evaluate_bomb(const PhantomBombSnapshot* s, PhantomBombTiming* out) {
    if (!sized(out)) return PHANTOM_INVALID_ARGUMENT;
    // Clear a valid output even on a bad/stale input, never leave an old timer.
    *out = {};
    out->struct_size = sizeof(*out);
    if (!sized(s) || s->valid > 1 || s->planted > 1 || s->defused > 1 || s->defusing > 1 || s->site > 2)
        return PHANTOM_INVALID_ARGUMENT;
    if (!s->valid) return PHANTOM_OK;
    if (!std::isfinite(s->game_time) || s->game_time < 0 ||
        !std::isfinite(s->observation_age) || s->observation_age < 0)
        return PHANTOM_INVALID_ARGUMENT;
    if (s->observation_age > stale_after) return PHANTOM_STALE_DATA;
    if ((!s->planted && (s->defused || s->defusing)) || (s->defused && s->defusing))
        return PHANTOM_INVALID_ARGUMENT;
    if (!s->planted) { out->phase = PHANTOM_BOMB_INACTIVE; return PHANTOM_OK; }
    if (s->defused) { out->phase = PHANTOM_BOMB_DEFUSED; out->site = s->site; return PHANTOM_OK; }
    if (!std::isfinite(s->detonation_time) || s->detonation_time <= 0 ||
        (s->defusing && (!std::isfinite(s->defuse_end_time) || s->defuse_end_time <= 0)))
        return PHANTOM_INVALID_ARGUMENT;
    out->site = s->site;
    out->explosion_remaining = std::max(0.0, s->detonation_time - s->game_time);
    if (out->explosion_remaining == 0) {
        // Timestamp elapsed, not proof that a server explosion event occurred.
        out->phase = PHANTOM_BOMB_EXPIRED;
        return PHANTOM_OK;
    }
    out->phase = s->defusing ? PHANTOM_BOMB_DEFUSING : PHANTOM_BOMB_TICKING;
    if (s->defusing) {
        out->defuse_remaining = std::max(0.0, s->defuse_end_time - s->game_time);
        // An elapsed end timestamp alone cannot establish a completed defuse.
        if (s->defuse_end_time > s->game_time) {
            const double delta = s->detonation_time - s->defuse_end_time;
            const double uncertainty = estimate_margin + s->observation_age;
            if (delta > uncertainty) out->defuse_estimate = PHANTOM_DEFUSE_EXPECTED_BEFORE;
            else if (delta < -uncertainty) out->defuse_estimate = PHANTOM_DEFUSE_EXPECTED_AFTER;
        }
    }
    return PHANTOM_OK;
}

int32_t PHANTOM_CALL phantom_set_cosmetic_preference(const PhantomCosmeticPreference* p) {
    if (!sized(p) || p->weapon_definition == 0 || p->weapon_definition > 65535 ||
        p->paint_kit > 0x7fffffffU || p->seed > 1000 || !std::isfinite(p->wear) ||
        p->wear < 0 || p->wear > 1 || p->stattrak < -1)
        return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        auto slot = std::find_if(store.entries.begin(), store.entries.end(),
                                 [p](const auto& entry) { return entry.weapon_definition == p->weapon_definition; });
        if (slot == store.entries.end())
            slot = std::find_if(store.entries.begin(), store.entries.end(),
                                [](const auto& entry) { return entry.weapon_definition == 0; });
        if (slot == store.entries.end()) return PHANTOM_CAPACITY_REACHED;
        *slot = *p;
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_get_cosmetic_preference(uint32_t weapon, PhantomCosmeticPreference* out) {
    if (!sized(out)) return PHANTOM_INVALID_ARGUMENT;
    *out = {};
    out->struct_size = sizeof(*out);
    if (!weapon || weapon > 65535) return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (const auto& entry : store.entries) {
            if (entry.weapon_definition == weapon) { *out = entry; return PHANTOM_OK; }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_clear_cosmetic_preferences(void) {
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        store.entries = {};
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_apply_cosmetics(void) {
    return PHANTOM_NOT_INTEGRATED;
}
