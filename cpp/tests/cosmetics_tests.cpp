#include "phantom/cosmetics.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace {
int failures = 0;
int checks = 0;
void check(bool result, const char* message) {
    ++checks;
    if (!result) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

struct Adapter : phantom::CosmeticAdapter {
    phantom::CosmeticItem item{42, 7, true, {5, 1, 0.2f, -1}};
    int writes = 0, refreshes = 0;
    bool readable = true, fail_write_once = false, fail_refresh_once = false;
    bool read(std::uint64_t, phantom::CosmeticItem& out) override {
        if (!readable) return false;
        out = item;
        return true;
    }
    bool write(std::uint64_t, const phantom::CosmeticValues& value) override {
        ++writes;
        item.values = value;
        if (fail_write_once) { fail_write_once = false; return false; }
        return true;
    }
    bool refresh(std::uint64_t) override {
        ++refreshes;
        if (fail_refresh_once) { fail_refresh_once = false; return false; }
        return true;
    }
};

class FakeProcessMemory final : public phantom::IProcessMemory {
public:
    bool fail_writes = false;
    int fail_write_on_call = 0;
    int write_calls = 0;

    bool read(std::uintptr_t address, void* output, std::size_t size) const override {
        auto* dst = static_cast<std::uint8_t*>(output);
        for (std::size_t i = 0; i < size; ++i) {
            const auto it = bytes_.find(address + i);
            if (it == bytes_.end()) return false;
            dst[i] = it->second;
        }
        return true;
    }
    bool write(std::uintptr_t address, const void* input, std::size_t size) override {
        ++write_calls;
        if (fail_writes || (fail_write_on_call > 0 && write_calls == fail_write_on_call)) return false;
        const auto* src = static_cast<const std::uint8_t*>(input);
        for (std::size_t i = 0; i < size; ++i) bytes_[address + i] = src[i];
        return true;
    }
    template<class T> void put(std::uintptr_t address, const T& value) {
        const auto* src = reinterpret_cast<const std::uint8_t*>(&value);
        for (std::size_t i = 0; i < sizeof(T); ++i) bytes_[address + i] = src[i];
    }
    template<class T> T get(std::uintptr_t address) const {
        T value{};
        read(address, &value, sizeof(T));
        return value;
    }
    void put_bytes(std::uintptr_t address, const void* data, std::size_t size) {
        const auto* src = static_cast<const std::uint8_t*>(data);
        for (std::size_t i = 0; i < size; ++i) bytes_[address + i] = src[i];
    }

private:
    std::map<std::uintptr_t, std::uint8_t> bytes_;
};

struct SkinMemoryFixture {
    FakeProcessMemory memory;
    phantom::Profile profile = phantom::Profile::reference_26598758();
    std::uintptr_t base = 0x10000000;
    std::uintptr_t root = 0x20000000;
    std::uintptr_t chunk0 = 0x21000000;
    std::uintptr_t chunk1 = 0x22000000;
    std::uintptr_t local_controller = 0x30000000;
    std::uintptr_t local_pawn = 0x40000000;
    std::uintptr_t weapon_services = 0x45000000;
    std::uintptr_t weapon_list_data = 0x46000000;
    std::uint32_t stride = 0x70;
    std::uint32_t local_pawn_handle = (5u << 15) | 1001u;

    std::uintptr_t ak_ptr = 0x50000000;
    std::uintptr_t ak_scene = 0x50100000;
    std::uintptr_t ak_vm = 0x50200000;
    std::uintptr_t ak_vm_scene = 0x50300000;
    std::uint32_t ak_handle = (7u << 15) | 200u;
    std::uint32_t ak_vm_handle = (9u << 15) | 201u;

    std::uintptr_t deagle_ptr = 0x51000000;
    std::uintptr_t deagle_scene = 0x51100000;
    std::uint32_t deagle_handle = (11u << 15) | 202u;

    SkinMemoryFixture() {
        memory.put(base + profile.modules.entity_list, root);
        memory.put(base + profile.modules.local_player_pawn, local_pawn);
        memory.put(base + profile.modules.local_player_controller, local_controller);
        memory.put(root + profile.layout.chunk_offset, chunk0);
        memory.put(root + profile.layout.chunk_offset + 8, chunk1);

        place_entity(local_pawn_handle, local_pawn);
        memory.put(local_controller + profile.fields.pawn_handle, local_pawn_handle);
        memory.put<std::uint64_t>(local_controller + profile.skins.steam_id, 0x0110000112345678ULL);

        memory.put(local_pawn + profile.skins.weapon_services, weapon_services);
        memory.put<std::int32_t>(weapon_services + profile.skins.my_weapons, 2);
        memory.put(weapon_services + profile.skins.my_weapons + 8, weapon_list_data);
        memory.put(weapon_list_data, ak_handle);
        memory.put(weapon_list_data + 4, deagle_handle);
        memory.put(weapon_services + profile.skins.active_weapon, ak_handle);

        setup_weapon(ak_handle, ak_ptr, ak_scene, 7, 10, 2, 0.25f, -1, 0x00010000u, 100u, 4, "orig-ak", 1ULL, ak_vm_handle, ak_vm, ak_vm_scene);
        setup_weapon(deagle_handle, deagle_ptr, deagle_scene, 1, 0, 0, 0.1f, -1, 0x00020000u, 200u, 0, "", 1ULL, 0, 0, 0);
    }

    std::uintptr_t entry_addr(std::uint32_t handle) const {
        const std::uint32_t idx = handle & profile.layout.handle_mask;
        const std::uintptr_t chunk = idx < 512 ? chunk0 : chunk1;
        return chunk + static_cast<std::uintptr_t>(stride) * (idx % 512);
    }

    void place_entity(std::uint32_t handle, std::uintptr_t ptr) {
        const std::uintptr_t entry = entry_addr(handle);
        memory.put(entry, ptr);
        memory.put(entry + profile.skins.identity_handle, handle);
        memory.put(ptr + profile.skins.entity_identity, entry);
    }

    void setup_weapon(std::uint32_t handle, std::uintptr_t ptr, std::uintptr_t scene,
                      std::uint16_t def, std::int32_t kit, std::int32_t seed, float wear, std::int32_t stattrak,
                      std::uint32_t item_id_high, std::uint32_t account_id, std::int32_t quality,
                      const char* orig_name, std::uint64_t mesh_mask,
                      std::uint32_t vm_handle, std::uintptr_t vm_ptr, std::uintptr_t vm_scene) {
        place_entity(handle, ptr);
        memory.put(ptr + profile.skins.owner_entity, local_pawn_handle);
        const std::uintptr_t item_view = ptr + profile.skins.attribute_manager + profile.skins.econ_item;
        memory.put(item_view + profile.skins.item_definition_index, def);
        memory.put(item_view + profile.skins.item_id_high, item_id_high);
        memory.put(item_view + profile.skins.account_id, account_id);
        memory.put(item_view + profile.skins.entity_quality, quality);
        std::array<char, 33> name_buf{};
        const std::size_t name_len = std::min<std::size_t>(std::strlen(orig_name), 32);
        std::memcpy(name_buf.data(), orig_name, name_len);
        memory.put_bytes(item_view + profile.skins.custom_name, name_buf.data(), name_buf.size());

        memory.put<std::uint32_t>(ptr + profile.skins.original_owner_xuid_low, 0x12345678u);
        memory.put(ptr + profile.skins.fallback_paint_kit, kit);
        memory.put(ptr + profile.skins.fallback_seed, seed);
        memory.put(ptr + profile.skins.fallback_wear, wear);
        memory.put(ptr + profile.skins.fallback_stattrak, stattrak);
        memory.put<std::int32_t>(ptr + profile.skins.custom_econ_reload_id, 5);
        memory.put(ptr + profile.fields.scene, scene);
        memory.put(scene + profile.fields.model_state + profile.skins.mesh_group_mask, mesh_mask);
        memory.put(ptr + profile.skins.viewmodel_attachment, vm_handle);
        if (vm_handle && vm_ptr && vm_scene) {
            place_entity(vm_handle, vm_ptr);
            memory.put(vm_ptr + profile.fields.scene, vm_scene);
            memory.put(vm_scene + profile.fields.model_state + profile.skins.mesh_group_mask, mesh_mask);
        }
    }
};

PhantomCosmeticPreference pref(std::uint32_t weapon = 7, std::uint32_t kit = 123) {
    return {sizeof(PhantomCosmeticPreference), weapon, kit, 20, 0.1f, 44};
}

void controller_tests() {
    Adapter a;
    phantom::CosmeticController controller;
    auto p = pref();
    check(controller.apply(a, 42, p) == PHANTOM_OK && a.item.values.paint_kit == 123 &&
          a.item.values.stattrak == 44 && a.refreshes == 1, "apply and refresh");
    p.paint_kit = 456;
    check(controller.apply(a, 42, p) == PHANTOM_OK && a.item.values.paint_kit == 456, "update");
    check(controller.restore(a, 42) == PHANTOM_OK && a.item.values.paint_kit == 5 &&
          a.item.values.seed == 1 && a.item.values.stattrak == -1, "restore original, not prior override");
    check(controller.restore(a, 42) == PHANTOM_NOT_FOUND, "restore removes baseline");

    a.fail_write_once = true;
    check(controller.apply(a, 42, p) == PHANTOM_INTERNAL_ERROR && a.item.values.paint_kit == 5,
          "partial failed write rolled back");
    check(controller.restore(a, 42) == PHANTOM_OK, "baseline retained after failure");
    a.fail_refresh_once = true;
    check(controller.apply(a, 42, p) == PHANTOM_INTERNAL_ERROR && a.item.values.paint_kit == 5,
          "failed refresh rolled back");
    check(controller.restore(a, 42) == PHANTOM_OK, "baseline retained after failed refresh");

    const int writes_before = a.writes;
    a.item.owned_local = false;
    check(controller.apply(a, 42, p) == PHANTOM_STALE_DATA && a.writes == writes_before,
          "refuse non-local item");
    a.item.owned_local = true;
    a.item.identity = 43;
    check(controller.apply(a, 42, p) == PHANTOM_STALE_DATA && a.writes == writes_before,
          "refuse recycled identity");
    a.item.identity = 42;
    p.wear = std::numeric_limits<float>::quiet_NaN();
    check(controller.apply(a, 42, p) == PHANTOM_INVALID_ARGUMENT && a.writes == writes_before,
          "reject invalid preference");
    p = pref();
    check(controller.apply(a, 42, p) == PHANTOM_OK, "apply before ownership loss");
    a.item.owned_local = false;
    const int after_apply = a.writes;
    check(controller.restore(a, 42) == PHANTOM_STALE_DATA && a.writes == after_apply,
          "do not restore dropped item");
    check(controller.restore(a, 42) == PHANTOM_NOT_FOUND, "forget dropped item");
}

void memory_adapter_tests() {
    SkinMemoryFixture fx;
    int material_refreshes = 0;
    bool fail_material_refresh = false;
    phantom::MemoryCosmeticAdapter adapter(
        fx.memory, fx.base, fx.profile,
        [&](std::uintptr_t) {
            ++material_refreshes;
            return !fail_material_refresh;
        });

    std::vector<phantom::CosmeticItem> weapons;
    check(adapter.enumerate_local_weapons(weapons) && weapons.size() == 2,
          "enumerates local weapons from m_hMyWeapons");
    check(weapons[0].weapon_definition == 7 && weapons[1].weapon_definition == 1,
          "decodes weapon definitions accurately");

    phantom::CosmeticController controller;
    phantom::CosmeticPreferenceEntry ak_entry{pref(7, 282), {"phantom-ak", 2}};
    phantom::CosmeticPreferenceEntry deagle_entry{pref(1, 37), {"", 1}};
    deagle_entry.preference.stattrak = -1;
    deagle_entry.preference.wear = 0.005f;
    deagle_entry.preference.seed = 420;

    phantom::CosmeticRunReport report{};
    check(controller.apply_loadout(adapter, {ak_entry, deagle_entry}, report) == PHANTOM_OK,
          "apply_loadout succeeds on owned local weapons");
    check(report.weapons_found == 2 && report.weapons_applied == 2 && report.weapons_failed == 0,
          "apply_loadout counts applied weapons");
    check(material_refreshes == 2, "material refresh callback invoked per applied weapon");

    const std::uintptr_t ak_item = fx.ak_ptr + fx.profile.skins.attribute_manager + fx.profile.skins.econ_item;
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_paint_kit) == 282,
          "writes AK fallback paint kit");
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_seed) == 20,
          "writes AK fallback seed");
    check(std::fabs(fx.memory.get<float>(fx.ak_ptr + fx.profile.skins.fallback_wear) - 0.1f) < 1e-5f,
          "writes AK fallback wear");
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_stattrak) == 44,
          "writes AK StatTrak");
    check(fx.memory.get<std::uint32_t>(ak_item + fx.profile.skins.item_id_high) == 0xffffffffu,
          "sets m_iItemIDHigh = -1 for client fallback");
    check(fx.memory.get<std::uint32_t>(ak_item + fx.profile.skins.account_id) == 0x12345678u,
          "sets local account ID from controller SteamID");
    check(fx.memory.get<std::int32_t>(ak_item + fx.profile.skins.entity_quality) == 9,
          "sets StatTrak entity quality");
    char custom_name[33]{};
    fx.memory.read(ak_item + fx.profile.skins.custom_name, custom_name, sizeof(custom_name));
    check(std::strcmp(custom_name, "phantom-ak") == 0, "writes custom nametag");
    check(fx.memory.get<std::uint64_t>(fx.ak_scene + fx.profile.fields.model_state + fx.profile.skins.mesh_group_mask) == 2ULL,
          "updates weapon mesh group mask");
    check(fx.memory.get<std::uint64_t>(fx.ak_vm_scene + fx.profile.fields.model_state + fx.profile.skins.mesh_group_mask) == 2ULL,
          "updates viewmodel attachment mesh group mask");
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.custom_econ_reload_id) == 6,
          "increments local econ reload event counter");

    // Second idempotent pass with identical loadout does not spam redundant writes/refreshes.
    const int writes_after_first = fx.memory.write_calls;
    check(controller.apply_loadout(adapter, {ak_entry, deagle_entry}, report) == PHANTOM_OK,
          "second idempotent apply_loadout succeeds");
    check(report.weapons_applied == 0 && fx.memory.write_calls == writes_after_first,
          "idempotent pass skips redundant writes");

    // Removing AK from loadout automatically restores AK to exact original baseline.
    check(controller.apply_loadout(adapter, {deagle_entry}, report) == PHANTOM_OK,
          "removing weapon from loadout restores it");
    check(report.weapons_restored == 1 && controller.active_count() == 1,
          "reports 1 restored weapon and retains remaining active weapon");
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_paint_kit) == 10 &&
          fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_seed) == 2 &&
          fx.memory.get<std::uint32_t>(ak_item + fx.profile.skins.item_id_high) == 0x00010000u &&
          fx.memory.get<std::uint32_t>(ak_item + fx.profile.skins.account_id) == 100u &&
          fx.memory.get<std::int32_t>(ak_item + fx.profile.skins.entity_quality) == 4,
          "AK fallback & econ metadata restored to exact original baseline");
    fx.memory.read(ak_item + fx.profile.skins.custom_name, custom_name, sizeof(custom_name));
    check(std::strcmp(custom_name, "orig-ak") == 0, "AK original custom name restored");
    check(fx.memory.get<std::uint64_t>(fx.ak_scene + fx.profile.fields.model_state + fx.profile.skins.mesh_group_mask) == 1ULL &&
          fx.memory.get<std::uint64_t>(fx.ak_vm_scene + fx.profile.fields.model_state + fx.profile.skins.mesh_group_mask) == 1ULL,
          "AK weapon and viewmodel mesh groups restored");

    // Failed material refresh rolls back partial apply cleanly.
    fail_material_refresh = true;
    check(controller.apply(adapter, fx.ak_handle, ak_entry.preference, ak_entry.extras) == PHANTOM_INTERNAL_ERROR,
          "failed material refresh returns error");
    check(fx.memory.get<std::int32_t>(fx.ak_ptr + fx.profile.skins.fallback_paint_kit) == 10 &&
          fx.memory.get<std::uint32_t>(ak_item + fx.profile.skins.item_id_high) == 0x00010000u,
          "failed refresh rolls back fallback fields and item_id_high");
    fail_material_refresh = false;

    // Recycled handle serial is refused (same slot index, new serial bits).
    const std::uint32_t recycled_handle = (99u << 15) | (fx.ak_handle & fx.profile.layout.handle_mask);
    fx.memory.put(fx.entry_addr(fx.ak_handle) + fx.profile.skins.identity_handle, recycled_handle);
    check(controller.apply(adapter, fx.ak_handle, ak_entry.preference, ak_entry.extras) == PHANTOM_STALE_DATA,
          "recycled handle serial is rejected");
    // Restore handle serial, then test dropped weapon (owner mismatch).
    fx.memory.put(fx.entry_addr(fx.ak_handle) + fx.profile.skins.identity_handle, fx.ak_handle);
    fx.memory.put<std::uint32_t>(fx.ak_ptr + fx.profile.skins.owner_entity, 0xffffffffu);
    check(controller.apply(adapter, fx.ak_handle, ak_entry.preference, ak_entry.extras) == PHANTOM_STALE_DATA,
          "dropped weapon without local owner is rejected");

    // restore_all restores the remaining Deagle.
    check(controller.restore_all(adapter, report) == PHANTOM_OK && report.weapons_restored == 1 &&
          controller.active_count() == 0, "restore_all restores remaining weapon");
    check(fx.memory.get<std::int32_t>(fx.deagle_ptr + fx.profile.skins.fallback_paint_kit) == 0,
          "Deagle restored to original paint kit");

    // Ambiguous entity stride calibration fails closed.
    const std::uint32_t pawn_idx = fx.local_pawn_handle & fx.profile.layout.handle_mask;
    fx.memory.put(fx.chunk1 + static_cast<std::uintptr_t>(0x78) * (pawn_idx % 512), fx.local_pawn);
    check(!adapter.enumerate_local_weapons(weapons), "ambiguous entity stride fails closed");
}

void loadout_json_tests() {
    bool enabled = false;
    std::vector<phantom::CosmeticPreferenceEntry> entries;
    const std::string valid_json = R"({
        "version": 1,
        "enabled": true,
        "entries": [
            {
                "weapon_definition": 7,
                "paint_kit": 282,
                "seed": 420,
                "wear": 0.15,
                "stattrak": 1337,
                "custom_name": "phantom \"red\"",
                "mesh_group": 2
            },
            {
                "weapon_definition": 9,
                "paint_kit": 344,
                "seed": 0,
                "wear": 0.001,
                "stattrak": -1,
                "custom_name": "",
                "mesh_group": 0
            }
        ]
    })";
    check(phantom::parse_skin_loadout_json(valid_json, enabled, entries), "valid loadout json parses");
    check(enabled && entries.size() == 2 &&
          entries[0].preference.weapon_definition == 7 && entries[0].preference.paint_kit == 282 &&
          entries[0].preference.stattrak == 1337 && entries[0].extras.custom_name == "phantom \"red\"" &&
          entries[0].extras.mesh_group_mask == 2 &&
          entries[1].preference.weapon_definition == 9 && entries[1].preference.paint_kit == 344,
          "loadout json values decoded accurately");

    // Disabled empty loadout is valid.
    check(phantom::parse_skin_loadout_json(R"({"version":1,"enabled":false,"entries":[]})", enabled, entries) &&
          !enabled && entries.empty(), "disabled empty loadout parses");

    // Invalid cases must fail without mutating output.
    enabled = true;
    entries = {{pref(7, 282), {"keep", 1}}};
    const char* bad_inputs[] = {
        R"({"version":2,"enabled":true,"entries":[]})",
        R"({"version":1,"enabled":"yes","entries":[]})",
        R"({"version":1,"enabled":true,"entries":[],"extra":1})",
        R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":1,"seed":0,"wear":0.1,"stattrak":-1},{"weapon_definition":7,"paint_kit":2,"seed":0,"wear":0.1,"stattrak":-1}]})",
        R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":1,"seed":1001,"wear":0.1,"stattrak":-1}]})",
        R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":1,"seed":0,"wear":1.5,"stattrak":-1}]})",
        R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":1,"seed":0,"wear":0.1,"stattrak":-1,"mesh_group":3}]})",
        R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":1,"seed":0,"wear":0.1,"stattrak":-1,"custom_name":"this name is far longer than thirty-two characters"}]})",
        R"({"version":1,"enabled":true,"entries":[]} trailing)"
    };
    for (const char* bad : bad_inputs) {
        check(!phantom::parse_skin_loadout_json(bad, enabled, entries), "reject invalid loadout json");
    }
    check(enabled && entries.size() == 1 && entries[0].extras.custom_name == "keep",
          "failed parse does not mutate caller output");

    // knife_override JSON parsing.
    std::uint32_t knife_override = 0;
    const std::string knife_json = R"({
        "version": 1,
        "enabled": true,
        "knife_override": 507,
        "entries": [
            {
                "weapon_definition": 507,
                "paint_kit": 415,
                "seed": 387,
                "wear": 0.01,
                "stattrak": 77,
                "custom_name": "ruby blade",
                "mesh_group": 1
            }
        ]
    })";
    check(phantom::parse_skin_loadout_json(knife_json, enabled, entries, knife_override) &&
          enabled && knife_override == 507 && entries.size() == 1 &&
          entries[0].preference.weapon_definition == 507 && entries[0].preference.paint_kit == 415,
          "loadout json with knife_override parses cleanly");
    check(phantom::parse_skin_loadout_json(R"({"version":1,"enabled":true,"knife_override":0,"entries":[]})",
                                           enabled, entries, knife_override) &&
          knife_override == 0, "loadout json with knife_override=0 parses cleanly");
    knife_override = 515;
    check(!phantom::parse_skin_loadout_json(R"({"version":1,"enabled":true,"knife_override":7,"entries":[]})",
                                            enabled, entries, knife_override) &&
          knife_override == 515, "non-knife weapon rejected in knife_override without mutating output");
    check(!phantom::parse_skin_loadout_json(R"({"version":1,"enabled":true,"knife_override":42,"entries":[]})",
                                            enabled, entries, knife_override) &&
          knife_override == 515, "default CT knife rejected as custom knife_override");
}

void knife_override_tests() {
    // Verify all 20 CS2 custom knives are recognized with canonical .vmdl paths and unique subclass tokens.
    const std::uint32_t all_knives[] = {
        500, 503, 505, 506, 507, 508, 509, 512, 514, 515,
        516, 517, 518, 519, 520, 521, 522, 523, 525, 526,
    };
    std::set<std::uint32_t> tokens;
    for (std::uint32_t id : all_knives) {
        check(phantom::is_custom_knife_definition(id) && phantom::is_knife_definition(id),
              "custom knife ID recognized");
        const char* vmdl = phantom::knife_model_path(id);
        check(vmdl != nullptr && std::strstr(vmdl, ".vmdl") != nullptr, "custom knife has .vmdl path");
        const std::string s = std::to_string(id);
        const std::uint32_t tok = phantom::utl_string_token(s.c_str());
        check(tok != 0 && tokens.insert(tok).second, "custom knife subclass token is non-zero and unique");
    }
    check(phantom::is_knife_definition(42) && !phantom::is_custom_knife_definition(42),
          "default CT knife recognized as knife but not custom target");
    check(phantom::is_knife_definition(59) && !phantom::is_custom_knife_definition(59),
          "default T knife recognized as knife but not custom target");
    check(!phantom::is_knife_definition(7) && !phantom::is_custom_knife_definition(7) &&
          phantom::knife_model_path(7) == nullptr, "AK-47 is not a knife");

    // MemoryCosmeticAdapter + CosmeticController knife swap, switch, idempotency, and full restore.
    SkinMemoryFixture fx;
    const std::uintptr_t knife_ptr = 0x52000000;
    const std::uintptr_t knife_scene = 0x52100000;
    const std::uintptr_t knife_vm = 0x52200000;
    const std::uintptr_t knife_vm_scene = 0x52300000;
    const std::uint32_t knife_handle = (15u << 15) | 205u;
    const std::uint32_t knife_vm_handle = (16u << 15) | 206u;

    fx.memory.put<std::int32_t>(fx.weapon_services + fx.profile.skins.my_weapons, 3);
    fx.memory.put(fx.weapon_list_data + 8, knife_handle);
    fx.setup_weapon(knife_handle, knife_ptr, knife_scene, 42, 0, 0, 0.0f, -1,
                    0x00030000u, 300u, 4, "", 1ULL, knife_vm_handle, knife_vm, knife_vm_scene);
    const std::uint32_t orig_subclass = phantom::utl_string_token("42");
    fx.memory.put(knife_ptr + fx.profile.skins.subclass_id, orig_subclass);

    int model_hooks = 0;
    std::uint32_t last_hook_def = 0;
    std::string last_hook_model;
    phantom::MemoryCosmeticAdapter adapter(
        fx.memory, fx.base, fx.profile, nullptr,
        [&](std::uintptr_t w, std::uintptr_t vm, std::uint32_t def, const char* vmdl) {
            if (w != knife_ptr || vm != knife_vm) return false;
            ++model_hooks;
            last_hook_def = def;
            last_hook_model = vmdl ? vmdl : "";
            return true;
        });

    phantom::CosmeticController controller;
    phantom::CosmeticPreferenceEntry karambit_entry{
        {sizeof(PhantomCosmeticPreference), 507, 415, 387, 0.01f, 77},
        {"ruby karambit", 1, 0},
    };
    phantom::CosmeticRunReport report{};
    check(controller.apply_loadout(adapter, {karambit_entry}, report, 507) == PHANTOM_OK &&
          report.weapons_found == 3 && report.weapons_applied == 1 && report.weapons_failed == 0,
          "knife_override applies Karambit Doppler Ruby onto default CT knife");

    const std::uintptr_t knife_item = knife_ptr + fx.profile.skins.attribute_manager + fx.profile.skins.econ_item;
    check(fx.memory.get<std::uint16_t>(knife_item + fx.profile.skins.item_definition_index) == 507,
          "item_definition_index swapped from 42 to 507");
    check(fx.memory.get<std::uint32_t>(knife_ptr + fx.profile.skins.subclass_id) == phantom::utl_string_token("507"),
          "m_nSubclassID updated to MurmurHash2(\"507\")");
    check(fx.memory.get<std::int32_t>(knife_item + fx.profile.skins.entity_quality) == 3,
          "knife entity_quality set to 3 (star unusual)");
    check(fx.memory.get<std::int32_t>(knife_ptr + fx.profile.skins.fallback_paint_kit) == 415 &&
          fx.memory.get<std::int32_t>(knife_ptr + fx.profile.skins.fallback_seed) == 387 &&
          fx.memory.get<std::int32_t>(knife_ptr + fx.profile.skins.fallback_stattrak) == 77,
          "knife fallback paint kit, seed, and StatTrak written");
    check(model_hooks == 1 && last_hook_def == 507 &&
          last_hook_model == "weapons/models/knife/knife_karambit/weapon_knife_karambit.vmdl",
          "optional knife model hook invoked with Karambit .vmdl");

    // Second pass is idempotent — no redundant writes or hooks.
    check(controller.apply_loadout(adapter, {karambit_entry}, report, 507) == PHANTOM_OK &&
          report.weapons_applied == 0 && model_hooks == 1,
          "repeated knife apply_loadout is idempotent");

    // Switching knife_override to Butterfly (515) with NO loadout entry applies Vanilla Butterfly cleanly!
    check(controller.apply_loadout(adapter, {}, report, 515) == PHANTOM_OK &&
          report.weapons_applied == 1 && report.weapons_restored == 0,
          "switching knife_override to Butterfly applies Vanilla Butterfly");
    check(fx.memory.get<std::uint16_t>(knife_item + fx.profile.skins.item_definition_index) == 515 &&
          fx.memory.get<std::uint32_t>(knife_ptr + fx.profile.skins.subclass_id) == phantom::utl_string_token("515") &&
          fx.memory.get<std::int32_t>(knife_ptr + fx.profile.skins.fallback_paint_kit) == 0 &&
          model_hooks == 2 && last_hook_def == 515 &&
          last_hook_model == "weapons/models/knife/knife_butterfly/weapon_knife_butterfly.vmdl",
          "Butterfly definition, subclass token, vanilla paint_kit, and .vmdl hook updated");

    // Clearing knife_override back to 0 restores the exact original default CT knife (42)!
    check(controller.apply_loadout(adapter, {}, report, 0) == PHANTOM_OK &&
          report.weapons_restored == 1 && controller.active_count() == 0,
          "clearing knife_override restores default CT knife");
    check(fx.memory.get<std::uint16_t>(knife_item + fx.profile.skins.item_definition_index) == 42 &&
          fx.memory.get<std::uint32_t>(knife_ptr + fx.profile.skins.subclass_id) == orig_subclass &&
          fx.memory.get<std::int32_t>(knife_item + fx.profile.skins.entity_quality) == 4 &&
          fx.memory.get<std::uint32_t>(knife_item + fx.profile.skins.item_id_high) == 0x00030000u &&
          model_hooks == 3 && last_hook_def == 42 &&
          last_hook_model == "weapons/models/knife/knife_default_ct/weapon_knife_default_ct.vmdl",
          "default CT knife definition, subclass token, quality, and .vmdl fully restored");
}
} // namespace

int main() {
    controller_tests();
    memory_adapter_tests();
    loadout_json_tests();
    knife_override_tests();
    if (failures) return 1;
    std::printf("cosmetic controller & memory adapter tests passed (%d checks)\n", checks);
    return 0;
}
