#include "phantom/cosmetics.h"
#include <algorithm>
#include <cmath>

namespace phantom {
namespace {
bool valid_values(const CosmeticValues& value) {
    return value.paint_kit <= 0x7fffffffu && value.seed <= 1000 &&
           std::isfinite(value.wear) && value.wear >= 0 && value.wear <= 1 &&
           value.stattrak >= -1;
}
bool matching(const CosmeticItem& item, std::uint64_t identity, std::uint32_t definition) {
    return item.identity == identity && item.owned_local && item.weapon_definition == definition;
}
}

int32_t CosmeticController::apply(CosmeticAdapter& adapter, std::uint64_t identity,
                                  const PhantomCosmeticPreference& preference) {
    const CosmeticValues desired{preference.paint_kit, preference.seed, preference.wear, preference.stattrak};
    if (!identity || preference.struct_size != sizeof(preference) || !preference.weapon_definition ||
        preference.weapon_definition > 65535 || !valid_values(desired)) return PHANTOM_INVALID_ARGUMENT;
    try {
        CosmeticItem current{};
        if (!adapter.read(identity, current) || !matching(current, identity, preference.weapon_definition) ||
            !valid_values(current.values)) return PHANTOM_STALE_DATA;
        auto entry = std::find_if(entries_.begin(), entries_.end(),
                                  [identity](const Entry& e) { return e.identity == identity; });
        if (entry != entries_.end() && entry->weapon_definition != current.weapon_definition)
            return PHANTOM_STALE_DATA;
        if (entry == entries_.end()) {
            entry = std::find_if(entries_.begin(), entries_.end(), [](const Entry& e) { return !e.identity; });
            if (entry == entries_.end()) return PHANTOM_CAPACITY_REACHED;
            *entry = {identity, current.weapon_definition, current.values};
        }
        if (adapter.write(identity, desired) && adapter.refresh(identity)) return PHANTOM_OK;
        // Keep the original baseline even after failure so restore can be retried.
        // Re-read before rollback: the slot may now belong to a different entity.
        CosmeticItem after{};
        if (adapter.read(identity, after) && matching(after, identity, entry->weapon_definition)) {
            if (adapter.write(identity, current.values)) adapter.refresh(identity);
        }
        return PHANTOM_INTERNAL_ERROR;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t CosmeticController::restore(CosmeticAdapter& adapter, std::uint64_t identity) {
    if (!identity) return PHANTOM_INVALID_ARGUMENT;
    auto entry = std::find_if(entries_.begin(), entries_.end(),
                              [identity](const Entry& e) { return e.identity == identity; });
    if (entry == entries_.end()) return PHANTOM_NOT_FOUND;
    try {
        CosmeticItem current{};
        if (!adapter.read(identity, current)) return PHANTOM_STALE_DATA;
        if (!matching(current, identity, entry->weapon_definition)) {
            // Never restore a recycled handle or a dropped weapon. Its old address
            // is no longer ours; forget the baseline rather than touching it.
            *entry = {};
            return PHANTOM_STALE_DATA;
        }
        if (!adapter.write(identity, entry->baseline) || !adapter.refresh(identity)) return PHANTOM_INTERNAL_ERROR;
        *entry = {};
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}
} // namespace phantom
