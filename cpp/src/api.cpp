#include "phantom/api.h"
#include "phantom/cosmetics.h"
#include "phantom/runtime.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace {
constexpr uint32_t abi = 1;
constexpr double stale_after = 0.5;
constexpr double estimate_margin = 0.1;

struct Store {
    std::mutex mutex;
    std::array<phantom::CosmeticPreferenceEntry, 32> entries{};
    std::uint32_t knife_override = 0;
};
Store& preferences() {
    // Construct only on an explicit API call, not under the DLL loader lock.
    static Store store;
    return store;
}
template<class T> bool sized(const T* value) {
    return value && value->struct_size == sizeof(T);
}
bool valid_preference(const PhantomCosmeticPreference* p) {
    return sized(p) && p->weapon_definition != 0 && p->weapon_definition <= 65535 &&
           p->paint_kit <= 0x7fffffffU && p->seed <= 1000 && std::isfinite(p->wear) &&
           p->wear >= 0.0f && p->wear <= 1.0f && p->stattrak >= -1 && p->stattrak <= 999999;
}
} // namespace

namespace phantom {
void snapshot_cosmetic_preferences(std::vector<CosmeticPreferenceEntry>& out) {
    out.clear();
    auto& store = preferences();
    std::lock_guard<std::mutex> lock(store.mutex);
    for (const auto& entry : store.entries) {
        if (entry.preference.weapon_definition != 0) out.push_back(entry);
    }
}

std::uint32_t snapshot_knife_override() {
    auto& store = preferences();
    std::lock_guard<std::mutex> lock(store.mutex);
    return store.knife_override;
}

int32_t replace_cosmetic_preferences(const std::vector<CosmeticPreferenceEntry>& entries,
                                     std::uint32_t knife_override) {
    if (entries.size() > 32) return PHANTOM_CAPACITY_REACHED;
    if (knife_override != 0 && !is_custom_knife_definition(knife_override))
        return PHANTOM_INVALID_ARGUMENT;
    for (const auto& entry : entries) {
        if (!valid_preference(&entry.preference) ||
            !valid_custom_name(entry.extras.custom_name) ||
            !valid_mesh_group(entry.extras.mesh_group_mask)) {
            return PHANTOM_INVALID_ARGUMENT;
        }
    }
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        store.entries = {};
        for (std::size_t i = 0; i < entries.size(); ++i) {
            store.entries[i] = entries[i];
        }
        store.knife_override = knife_override;
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}
} // namespace phantom

uint32_t PHANTOM_CALL phantom_abi_version(void) { return abi; }

int32_t PHANTOM_CALL phantom_get_integration_status(PhantomIntegrationStatus* out) {
    if (!sized(out)) return PHANTOM_INVALID_ARGUMENT;
    *out = {};
    out->struct_size = sizeof(*out);
    out->abi_version = abi;
    constexpr char reason[] =
        "Experimental bomb and local skin adapters require in-process client.dll and are not live-validated.";
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
    if (!valid_preference(p)) return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        auto slot = std::find_if(store.entries.begin(), store.entries.end(),
                                 [p](const auto& entry) {
                                     return entry.preference.weapon_definition == p->weapon_definition;
                                 });
        if (slot == store.entries.end()) {
            slot = std::find_if(store.entries.begin(), store.entries.end(),
                                [](const auto& entry) { return entry.preference.weapon_definition == 0; });
            if (slot == store.entries.end()) return PHANTOM_CAPACITY_REACHED;
            slot->extras = {};
        }
        slot->preference = *p;
        phantom::set_skin_loadout_enabled(true);
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
            if (entry.preference.weapon_definition == weapon) {
                *out = entry.preference;
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_remove_cosmetic_preference(uint32_t weapon) {
    if (!weapon || weapon > 65535) return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (auto& entry : store.entries) {
            if (entry.preference.weapon_definition == weapon) {
                entry = {};
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_list_cosmetic_preferences(PhantomCosmeticPreference* out,
                                                       uint32_t capacity, uint32_t* out_count) {
    if (!out_count || (capacity > 0 && !out)) return PHANTOM_INVALID_ARGUMENT;
    *out_count = 0;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        uint32_t total = 0;
        for (const auto& entry : store.entries) {
            if (entry.preference.weapon_definition == 0) continue;
            if (total < capacity) out[total] = entry.preference;
            ++total;
        }
        *out_count = total;
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_set_cosmetic_custom_name(uint32_t weapon, const char* custom_name) {
    if (!weapon || weapon > 65535 || !custom_name) return PHANTOM_INVALID_ARGUMENT;
    try {
        const std::string value(custom_name);
        if (!phantom::valid_custom_name(value)) return PHANTOM_INVALID_ARGUMENT;
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (auto& entry : store.entries) {
            if (entry.preference.weapon_definition == weapon) {
                entry.extras.custom_name = value;
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_get_cosmetic_custom_name(uint32_t weapon, char* out, uint32_t out_capacity) {
    if (!out || out_capacity == 0) return PHANTOM_INVALID_ARGUMENT;
    out[0] = '\0';
    if (!weapon || weapon > 65535) return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (const auto& entry : store.entries) {
            if (entry.preference.weapon_definition == weapon) {
                const std::string& name = entry.extras.custom_name;
                if (name.size() + 1 > out_capacity) return PHANTOM_CAPACITY_REACHED;
                std::memcpy(out, name.c_str(), name.size() + 1);
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_set_cosmetic_mesh_group(uint32_t weapon, uint64_t mesh_group_mask) {
    if (!weapon || weapon > 65535 || !phantom::valid_mesh_group(mesh_group_mask))
        return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (auto& entry : store.entries) {
            if (entry.preference.weapon_definition == weapon) {
                entry.extras.mesh_group_mask = mesh_group_mask;
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_get_cosmetic_mesh_group(uint32_t weapon, uint64_t* out_mask) {
    if (!out_mask) return PHANTOM_INVALID_ARGUMENT;
    *out_mask = 0;
    if (!weapon || weapon > 65535) return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        for (const auto& entry : store.entries) {
            if (entry.preference.weapon_definition == weapon) {
                *out_mask = entry.extras.mesh_group_mask;
                return PHANTOM_OK;
            }
        }
        return PHANTOM_NOT_FOUND;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_set_knife_override(uint32_t knife_definition) {
    if (knife_definition != 0 && !phantom::is_custom_knife_definition(knife_definition))
        return PHANTOM_INVALID_ARGUMENT;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        store.knife_override = knife_definition;
        if (knife_definition != 0) phantom::set_skin_loadout_enabled(true);
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_get_knife_override(uint32_t* out_knife_definition) {
    if (!out_knife_definition) return PHANTOM_INVALID_ARGUMENT;
    *out_knife_definition = 0;
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        *out_knife_definition = store.knife_override;
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_clear_cosmetic_preferences(void) {
    try {
        auto& store = preferences();
        std::lock_guard<std::mutex> lock(store.mutex);
        store.entries = {};
        store.knife_override = 0;
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t PHANTOM_CALL phantom_apply_cosmetics(void) {
    PhantomSkinApplyReport report{};
    report.struct_size = sizeof(report);
    return phantom_runtime_apply_skins(&report);
}

int32_t PHANTOM_CALL phantom_restore_cosmetics(void) {
    PhantomSkinApplyReport report{};
    report.struct_size = sizeof(report);
    return phantom_runtime_restore_skins(&report);
}
