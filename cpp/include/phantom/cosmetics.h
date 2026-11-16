#pragma once

#include "phantom/api.h"
#include "phantom/core.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace phantom {

// The host must resolve a full, serial-bearing entity handle and verify local
// ownership on every call, including write and refresh. Calls must run on
// the game's owning thread and must not throw.
struct CosmeticValues {
    std::uint32_t paint_kit = 0;
    std::uint32_t seed = 0;
    float wear = 0;
    std::int32_t stattrak = -1;
};
struct CosmeticExtras {
    std::string custom_name;
    std::uint64_t mesh_group_mask = 0; // 0 = auto/unchanged, 1 = modern, 2 = legacy
};
struct CosmeticPreferenceEntry {
    PhantomCosmeticPreference preference{};
    CosmeticExtras extras{};
};
struct CosmeticItem {
    std::uint64_t identity = 0;
    std::uint32_t weapon_definition = 0;
    bool owned_local = false;
    CosmeticValues values{};
};
struct CosmeticRunReport {
    std::uint32_t weapons_found = 0;
    std::uint32_t weapons_applied = 0;
    std::uint32_t weapons_restored = 0;
    std::uint32_t weapons_failed = 0;
};

bool valid_custom_name(const std::string& name);
bool valid_mesh_group(std::uint64_t mask);
bool parse_skin_loadout_json(const std::string& text, bool& enabled_out,
                             std::vector<CosmeticPreferenceEntry>& entries_out);

class CosmeticAdapter {
public:
    virtual ~CosmeticAdapter() = default;
    virtual bool read(std::uint64_t identity, CosmeticItem& item) = 0;
    // A failing write may have partially changed the item.
    virtual bool write(std::uint64_t identity, const CosmeticValues& values) = 0;
    // Rebuild local weapon and viewmodel materials; never network inventory.
    virtual bool refresh(std::uint64_t identity) = 0;
    // Optional hooks for adapters that track per-weapon metadata or enumerate local weapons.
    virtual void set_pending_extras(std::uint64_t identity, const CosmeticExtras& extras) {
        (void)identity;
        (void)extras;
    }
    virtual void clear_pending_extras(std::uint64_t identity) { (void)identity; }
    virtual bool enumerate_local_weapons(std::vector<CosmeticItem>& out) {
        out.clear();
        return false;
    }
};

// Memory-backed local CS2 cosmetic adapter using pinned schema offsets.
// Verifies full serial-bearing handles and local ownership on every operation.
class MemoryCosmeticAdapter final : public CosmeticAdapter {
public:
    using MaterialRefreshFn = std::function<bool(std::uintptr_t)>;

    MemoryCosmeticAdapter(IProcessMemory& memory, std::uintptr_t client_base,
                          const Profile& profile, MaterialRefreshFn material_refresh = nullptr);

    bool enumerate_local_weapons(std::vector<CosmeticItem>& out) override;
    bool read(std::uint64_t identity, CosmeticItem& item) override;
    bool write(std::uint64_t identity, const CosmeticValues& values) override;
    bool refresh(std::uint64_t identity) override;
    void set_pending_extras(std::uint64_t identity, const CosmeticExtras& extras) override;
    void clear_pending_extras(std::uint64_t identity) override;

private:
    struct LocalContext {
        std::uintptr_t root = 0;
        std::uintptr_t local_pawn = 0;
        std::uintptr_t local_controller = 0;
        std::uint32_t stride = 0;
        std::uint32_t local_account_id = 0;
        std::vector<std::uint32_t> owned_handles;
    };
    struct OriginalMeta {
        std::int32_t raw_paint_kit = 0;
        std::int32_t raw_seed = 0;
        float raw_wear = 0.0f;
        std::int32_t raw_stattrak = -1;
        std::uint32_t item_id_high = 0;
        std::uint32_t account_id = 0;
        std::int32_t entity_quality = 0;
        bool has_custom_name = false;
        std::array<char, 33> original_name{};
        bool has_weapon_mesh = false;
        std::uint64_t weapon_mesh_group = 0;
        bool has_viewmodel_mesh = false;
        std::uint64_t viewmodel_mesh_group = 0;
    };
    struct PendingMode {
        bool override_active = false;
        CosmeticExtras extras{};
    };

    bool resolve_context(LocalContext& ctx) const;
    std::uintptr_t resolve_entity(std::uintptr_t root, std::uint32_t index, std::uint32_t stride) const;
    std::uintptr_t resolve_handle_with_serial(std::uintptr_t root, std::uint32_t handle,
                                              std::uint32_t stride) const;
    bool resolve_weapon(const LocalContext& ctx, std::uint64_t identity,
                        std::uintptr_t& weapon_out, bool& owned_local_out) const;
    bool read_mesh_group(std::uintptr_t entity_ptr, std::uint64_t& mask_out) const;
    bool write_mesh_group(std::uintptr_t entity_ptr, std::uint64_t mask);

    IProcessMemory& memory_;
    std::uintptr_t base_;
    Profile profile_;
    MaterialRefreshFn material_refresh_;
    std::map<std::uint64_t, OriginalMeta> originals_;
    std::map<std::uint64_t, PendingMode> pending_;
};

// A host owns this controller and calls it only on the game thread.
class CosmeticController {
public:
    int32_t apply(CosmeticAdapter& adapter, std::uint64_t identity,
                  const PhantomCosmeticPreference& preference);
    int32_t apply(CosmeticAdapter& adapter, std::uint64_t identity,
                  const PhantomCosmeticPreference& preference,
                  const CosmeticExtras& extras);
    int32_t restore(CosmeticAdapter& adapter, std::uint64_t identity);
    int32_t apply_loadout(CosmeticAdapter& adapter,
                          const std::vector<CosmeticPreferenceEntry>& loadout,
                          CosmeticRunReport& report);
    int32_t restore_all(CosmeticAdapter& adapter, CosmeticRunReport& report);
    std::size_t active_count() const;

private:
    struct Entry {
        std::uint64_t identity = 0;
        std::uint32_t weapon_definition = 0;
        CosmeticValues baseline{};
        bool had_override = false;
        CosmeticExtras active_extras{};
    };
    std::array<Entry, 32> entries_{};
};

// Internal shared preference-store accessors between api.cpp and runtime.cpp.
void snapshot_cosmetic_preferences(std::vector<CosmeticPreferenceEntry>& out);
int32_t replace_cosmetic_preferences(const std::vector<CosmeticPreferenceEntry>& entries);
void set_skin_loadout_enabled(bool enabled);

} // namespace phantom
