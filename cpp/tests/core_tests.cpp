#include "phantom/api.h"
#include "phantom/runtime.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>

static int failures = 0;
static uint32_t check_count = 0;

void check(bool condition, const char* message) {
    ++check_count;
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

PhantomBombSnapshot valid_planted() {
    PhantomBombSnapshot s{};
    s.struct_size = sizeof(s);
    s.valid = 1;
    s.planted = 1;
    s.site = 1;
    s.game_time = 100.0;
    s.detonation_time = 110.0;
    s.observation_age = 0.05;
    return s;
}

PhantomCosmeticPreference valid_preference(uint32_t weapon, uint32_t kit = 42) {
    PhantomCosmeticPreference p{};
    p.struct_size = sizeof(p);
    p.weapon_definition = weapon;
    p.paint_kit = kit;
    p.seed = 17;
    p.wear = 0.125f;
    p.stattrak = -1;
    return p;
}

void bomb_tests() {
    PhantomBombTiming timing{};
    timing.struct_size = sizeof(timing);
    timing.phase = 99; // hostile stale output: invalid input must clear it
    PhantomBombSnapshot invalid{};
    check(phantom_evaluate_bomb(nullptr, &timing) == PHANTOM_INVALID_ARGUMENT, "null snapshot rejected");
    check(timing.phase == PHANTOM_BOMB_UNAVAILABLE,
          "invalid input clears stale output");

    invalid.struct_size = sizeof(invalid);
    invalid.valid = 2; // unrecognized boolean
    check(phantom_evaluate_bomb(&invalid, &timing) == PHANTOM_INVALID_ARGUMENT,
          "unrecognized boolean value rejected");
    check(timing.phase == PHANTOM_BOMB_UNAVAILABLE,
          "rejected snapshot clears stale output");

    invalid = valid_planted();
    invalid.struct_size = 0;
    check(phantom_evaluate_bomb(&invalid, &timing) == PHANTOM_INVALID_ARGUMENT, "bad snapshot size rejected");

    auto bomb = valid_planted();
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK, "planted/unattended timer evaluates");
    check(timing.phase == PHANTOM_BOMB_TICKING && timing.site == 1, "unattended planted bomb ticks");
    check(std::fabs(timing.explosion_remaining - 10.0) < 0.0001, "explosion remainder calculated");

    bomb.defusing = 1;
    bomb.defuse_end_time = 106.0;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK, "defusing bomb evaluates");
    check(timing.phase == PHANTOM_BOMB_DEFUSING && timing.defuse_estimate == PHANTOM_DEFUSE_EXPECTED_BEFORE,
          "early uncontested estimate is reported separately");
    check(std::fabs(timing.defuse_remaining - 6.0) < 0.0001, "defuse remainder calculated");

    bomb.defuse_end_time = 112.0;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK &&
          timing.defuse_estimate == PHANTOM_DEFUSE_EXPECTED_AFTER,
          "late defuse estimate is reported separately");

    bomb.defuse_end_time = 110.05;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK &&
          timing.defuse_estimate == PHANTOM_DEFUSE_UNKNOWN,
          "near-boundary defuse estimate remains unknown");

    bomb = valid_planted();
    bomb.game_time = 110.0;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK &&
          timing.phase == PHANTOM_BOMB_EXPIRED && timing.explosion_remaining == 0.0,
          "elapsed timestamp reports expired without claiming observed explosion");

    bomb = valid_planted();
    bomb.defused = 1;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK && timing.phase == PHANTOM_BOMB_DEFUSED,
          "defused state wins before remaining timer");

    bomb = valid_planted();
    bomb.defusing = 1; // deliberately missing defuse_end_time
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_INVALID_ARGUMENT,
          "defusing state requires a defuse end timestamp");

    bomb = valid_planted();
    bomb.observation_age = 0.51;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_STALE_DATA && timing.phase == PHANTOM_BOMB_UNAVAILABLE,
          "stale capture cannot display an old timer");

    bomb.valid = 0;
    check(phantom_evaluate_bomb(&bomb, &timing) == PHANTOM_OK && timing.phase == PHANTOM_BOMB_UNAVAILABLE,
          "explicit unavailable snapshot stays unavailable");
}

void cosmetic_tests() {
    check(phantom_clear_cosmetic_preferences() == PHANTOM_OK, "preference cleanup starts from empty");
    PhantomCosmeticPreference p = valid_preference(7);
    check(phantom_set_cosmetic_preference(&p) == PHANTOM_OK, "preference accepted as data only");
    PhantomCosmeticPreference out{};
    out.struct_size = sizeof(out);
    check(phantom_get_cosmetic_preference(7, &out) == PHANTOM_OK, "preference retrieved");
    check(out.paint_kit == 42 && out.seed == 17 && std::fabs(out.wear - 0.125f) < 0.0001f,
          "preference round trip retains values");
    p.paint_kit = 99;
    check(phantom_set_cosmetic_preference(&p) == PHANTOM_OK, "same weapon updates one preference");
    check(phantom_get_cosmetic_preference(7, &out) == PHANTOM_OK && out.paint_kit == 99,
          "updated preference replaces prior value");
    check(phantom_get_cosmetic_preference(9999, &out) == PHANTOM_NOT_FOUND, "missing weapon not found");
    p.stattrak = -2;
    check(phantom_set_cosmetic_preference(&p) == PHANTOM_INVALID_ARGUMENT, "invalid stattrak rejected");
    p = valid_preference(7);
    p.wear = 1.25f;
    check(phantom_set_cosmetic_preference(&p) == PHANTOM_INVALID_ARGUMENT, "out-of-range wear rejected");
    check(phantom_apply_cosmetics() == PHANTOM_NOT_INTEGRATED,
          "cosmetic application fails closed without client.dll");
    check(phantom_restore_cosmetics() == PHANTOM_NOT_INTEGRATED,
          "cosmetic restore fails closed without client.dll");

    // Extras (custom name, mesh group), listing, and single-weapon removal.
    check(phantom_set_cosmetic_custom_name(7, "phantom redline") == PHANTOM_OK, "custom name accepted");
    char name_buf[64]{};
    check(phantom_get_cosmetic_custom_name(7, name_buf, sizeof(name_buf)) == PHANTOM_OK &&
          std::strcmp(name_buf, "phantom redline") == 0, "custom name round trips");
    check(phantom_set_cosmetic_custom_name(7, "name-with-\n-newline") == PHANTOM_INVALID_ARGUMENT,
          "control character in custom name rejected");
    check(phantom_set_cosmetic_custom_name(9999, "missing") == PHANTOM_NOT_FOUND,
          "custom name for absent weapon returns not found");
    check(phantom_set_cosmetic_mesh_group(7, 2) == PHANTOM_OK, "legacy mesh group accepted");
    uint64_t mask = 0;
    check(phantom_get_cosmetic_mesh_group(7, &mask) == PHANTOM_OK && mask == 2, "mesh group round trips");
    check(phantom_set_cosmetic_mesh_group(7, 5) == PHANTOM_INVALID_ARGUMENT, "invalid mesh group rejected");
    PhantomCosmeticPreference list_buf[4]{};
    uint32_t list_count = 0;
    check(phantom_list_cosmetic_preferences(list_buf, 4, &list_count) == PHANTOM_OK &&
          list_count == 1 && list_buf[0].weapon_definition == 7 && list_buf[0].paint_kit == 99,
          "list preferences returns stored weapons");
    check(phantom_remove_cosmetic_preference(7) == PHANTOM_OK &&
          phantom_get_cosmetic_preference(7, &out) == PHANTOM_NOT_FOUND,
          "single preference removal clears weapon");
    check(phantom_remove_cosmetic_preference(7) == PHANTOM_NOT_FOUND, "removing absent weapon reports not found");

    // Runtime skin APIs fail closed without client.dll, while JSON file loading validates cross-platform.
    PhantomSkinApplyReport report{};
    report.struct_size = sizeof(report);
    check(phantom_runtime_apply_skins(&report) == PHANTOM_NOT_INTEGRATED, "runtime apply fails closed without client.dll");
    check(phantom_runtime_restore_skins(&report) == PHANTOM_NOT_INTEGRATED, "runtime restore fails closed without client.dll");
    PhantomSkinWatcherOptions watcher{};
    watcher.struct_size = sizeof(watcher);
    watcher.poll_interval_ms = 200;
    watcher.restore_on_stop = 1;
    check(phantom_runtime_start_skin_watcher(&watcher) == PHANTOM_NOT_INTEGRATED, "watcher fails closed without client.dll");
    watcher.poll_interval_ms = 10;
    check(phantom_runtime_start_skin_watcher(&watcher) == PHANTOM_INVALID_ARGUMENT, "watcher rejects invalid poll interval");
    check(phantom_runtime_stop_skin_watcher() == PHANTOM_OK, "stopping idle watcher is safe");

    const auto tmp_path = std::filesystem::temp_directory_path() / "phantom_test_skin_loadout.json";
    {
        std::ofstream file(tmp_path, std::ios::binary);
        file << R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":282,"seed":420,"wear":0.15,"stattrak":1337,"custom_name":"ak-test","mesh_group":2}]})";
    }
    check(phantom_runtime_load_skin_file(tmp_path.u8string().c_str()) == PHANTOM_OK, "valid skin loadout file loads");
    check(phantom_get_cosmetic_preference(7, &out) == PHANTOM_OK && out.paint_kit == 282 && out.stattrak == 1337,
          "loaded file populates preference store");
    check(phantom_get_cosmetic_custom_name(7, name_buf, sizeof(name_buf)) == PHANTOM_OK &&
          std::strcmp(name_buf, "ak-test") == 0, "loaded file populates custom name");
    check(phantom_get_cosmetic_mesh_group(7, &mask) == PHANTOM_OK && mask == 2,
          "loaded file populates mesh group");
    {
        std::ofstream file(tmp_path, std::ios::binary);
        file << R"({"version":1,"enabled":true,"entries":[{"weapon_definition":7,"paint_kit":282,"seed":9999,"wear":0.15,"stattrak":-1}]})";
    }
    check(phantom_runtime_load_skin_file(tmp_path.u8string().c_str()) == PHANTOM_INVALID_ARGUMENT,
          "invalid loadout file rejected");
    check(phantom_get_cosmetic_preference(7, &out) == PHANTOM_OK && out.paint_kit == 282,
          "invalid loadout file preserves prior preferences");
    std::error_code ec;
    std::filesystem::remove(tmp_path, ec);

    // Fill every remaining slot after weapon 7, then verify overflow is explicit.
    for (uint32_t weapon = 100; weapon < 131; ++weapon) {
        p = valid_preference(weapon, weapon);
        check(phantom_set_cosmetic_preference(&p) == PHANTOM_OK, "preference store accepts unique weapon id");
    }
    p = valid_preference(999, 123);
    check(phantom_set_cosmetic_preference(&p) == PHANTOM_CAPACITY_REACHED,
          "preference store reports capacity instead of evicting silently");
    check(phantom_clear_cosmetic_preferences() == PHANTOM_OK &&
          phantom_get_cosmetic_preference(7, &out) == PHANTOM_NOT_FOUND,
          "clear removes all preferences");
}

int main() {
    PhantomIntegrationStatus status{};
    status.struct_size = sizeof(status);
    check(phantom_abi_version() == 1, "ABI version reported");
    check(phantom_get_integration_status(&status) == PHANTOM_OK, "integration status reports without a game");
    check(status.abi_version == 1 && status.game_adapter_ready == 0 &&
          status.live_bomb_timer_ready == 0 && status.cosmetic_changes_ready == 0,
          "foundation cannot masquerade as an integrated cheat");
    check(std::strlen(status.reason) > 0, "unavailable integration has a reason");
    bomb_tests();
    cosmetic_tests();
    if (failures == 0) {
        std::printf("cpp foundation: %u checks passed\n", check_count);
        return 0;
    }
    std::fprintf(stderr, "cpp foundation: %d of %u checks failed\n", failures, check_count);
    return 1;
}
