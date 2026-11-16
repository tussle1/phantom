#include "phantom/core.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <tuple>
#include <map>
#include <optional>
#include <vector>

static int failures = 0;
static std::uint32_t checks = 0;
static void check(bool condition, const char* message) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

class FakeMemory final : public phantom::IMemory {
public:
    void write(std::uintptr_t address, const void* data, std::size_t size) {
        const auto* bytes = static_cast<const std::uint8_t*>(data);
        for (std::size_t index = 0; index < size; ++index) bytes_[address + index] = bytes[index];
    }
    template<class T> void put(std::uintptr_t address, T value) { write(address, &value, sizeof(value)); }
    bool read(std::uintptr_t address, void* output, std::size_t size) const override {
        auto* bytes = static_cast<std::uint8_t*>(output);
        for (std::size_t index = 0; index < size; ++index) {
            const auto it = bytes_.find(address + index);
            if (it == bytes_.end()) return false;
            bytes[index] = it->second;
        }
        return true;
    }
private:
    std::map<std::uintptr_t, std::uint8_t> bytes_;
};

static phantom::Profile test_profile() {
    auto profile = phantom::Profile::reference_26598758();
    profile.source = std::string(40, 'a');
    profile.modules.entity_list = 0x10000;
    profile.modules.local_player_pawn = 0x10100;
    profile.modules.local_player_controller = 0x10200;
    profile.modules.view_matrix = 0x10300;
    profile.modules.view_angles = 0x10400;
    profile.modules.sensitivity = 0x10500;
    profile.modules.sensitivity_sensitivity = 0x58;
    profile.modules.game_rules = 0x10600;
    profile.modules.planted_c4 = 0x10700;
    profile.fields.health = 0x100;
    profile.fields.armor = 0x104;
    profile.fields.team = 0x108;
    profile.fields.scene = 0x110;
    profile.fields.velocity = 0x120;
    profile.fields.flags = 0x130;
    profile.fields.view_offset = 0x140;
    profile.fields.pawn_handle = 0x150;
    profile.fields.spotted_state = 0x160;
    profile.fields.spotted_mask = 8;
    profile.fields.crosshair = 0x180;
    profile.fields.observer_pawn = 0x190;
    profile.fields.observer_services = 0x198;
    profile.fields.observer_target = 0x20;
    profile.fields.name = 0x200;
    profile.fields.origin = 0x20;
    profile.fields.dormant = 0x40;
    profile.fields.model_state = 0x100;
    profile.fields.simulation_time = 0x400;
    profile.layout = {0x10, 512, 0x7fff, 0x80, 32, 64, {0x70, 0x78}};
    return profile;
}

struct Fixture {
    FakeMemory memory;
    phantom::Profile profile = test_profile();
    std::uintptr_t base = 0x10000000;
    std::uintptr_t root = 0x20000000, chunk0 = 0x21000000, chunk1 = 0x22000000;
    std::uintptr_t local_controller = 0x30000000, enemy_controller = 0x31000000;
    std::uintptr_t local_pawn = 0x40000000, enemy_pawn = 0x41000000;
    std::uintptr_t local_scene = 0x50000000, enemy_scene = 0x51000000, bone_array = 0x60000000;
    Fixture() {
        put_ref(base + profile.modules.entity_list, root);
        put_ref(base + profile.modules.local_player_pawn, local_pawn);
        put_ref(base + profile.modules.local_player_controller, local_controller);
        put_ref(base + profile.modules.game_rules, 0);
        put_ref(base + profile.modules.planted_c4, 0);
        put_ref(root + 0x10, chunk0);
        put_ref(root + 0x18, chunk1);
        constexpr std::uint32_t stride = 0x70;
        for (const auto& [index, address] : std::vector<std::pair<std::uint32_t, std::uintptr_t>>{
                 {1, local_controller}, {2, enemy_controller}, {1001, local_pawn}, {1002, enemy_pawn}}) {
            const std::uintptr_t chunk = index < 512 ? chunk0 : chunk1;
            put_ref(chunk + (index % 512) * stride, address);
        }
        memory.put(local_controller + profile.fields.pawn_handle, static_cast<std::uint32_t>(1001));
        memory.put(enemy_controller + profile.fields.pawn_handle, static_cast<std::uint32_t>(1002));
        std::uint8_t raw_name[128]{};
        static_assert(sizeof("fixture enemy") <= sizeof(raw_name));
        std::memcpy(raw_name, "fixture enemy", sizeof("fixture enemy") - 1);
        memory.write(enemy_controller + profile.fields.name, raw_name, sizeof(raw_name));
        for (const auto& [pawn, scene, x, z, team] : std::vector<std::tuple<std::uintptr_t, std::uintptr_t, float, float, std::uint8_t>>{
                 {local_pawn, local_scene, 0.0f, 0.0f, 2}, {enemy_pawn, enemy_scene, 100.0f, 0.0f, 3}}) {
            memory.put(pawn + profile.fields.health, static_cast<std::int32_t>(100));
            memory.put(pawn + profile.fields.armor, static_cast<std::int32_t>(80));
            memory.put<std::uint8_t>(pawn + profile.fields.team, team);
            put_ref(pawn + profile.fields.scene, scene);
            memory.put(pawn + profile.fields.velocity, 0.0f);
            memory.put(pawn + profile.fields.velocity + 4, 0.0f);
            memory.put(pawn + profile.fields.velocity + 8, 0.0f);
            memory.put(pawn + profile.fields.spotted_state + profile.fields.spotted_mask, static_cast<std::uint64_t>(1));
            memory.put(scene + profile.fields.origin, x);
            memory.put(scene + profile.fields.origin + 4, 0.0f);
            memory.put(scene + profile.fields.origin + 8, z);
            memory.put<std::uint8_t>(scene + profile.fields.dormant, 0);
        }
        put_ref(enemy_scene + profile.fields.model_state + profile.layout.bone_array, bone_array);
        std::vector<std::uint8_t> zeros(28 * profile.layout.bone_stride, 0);
        memory.write(bone_array, zeros.data(), zeros.size());
        phantom::Settings settings;
        for (const auto& [name, index] : settings.bones) {
            const float z = name == "head" ? 64.0f : 35.0f;
            memory.put(bone_array + static_cast<std::size_t>(index) * profile.layout.bone_stride, 100.0f);
            memory.put(bone_array + static_cast<std::size_t>(index) * profile.layout.bone_stride + 4, 0.0f);
            memory.put(bone_array + static_cast<std::size_t>(index) * profile.layout.bone_stride + 8, z);
        }
        memory.put(local_pawn + profile.fields.view_offset, 0.0f);
        memory.put(local_pawn + profile.fields.view_offset + 4, 0.0f);
        memory.put(local_pawn + profile.fields.view_offset + 8, 64.0f);
        memory.put(local_pawn + profile.fields.flags, static_cast<std::uint32_t>(1));
        memory.put(local_pawn + profile.fields.crosshair, static_cast<std::int32_t>(1002));
        memory.put(local_pawn + profile.fields.simulation_time, 123.5f);
        const float matrix[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
        memory.write(base + profile.modules.view_matrix, matrix, sizeof(matrix));
        const float view_angles[3] = {0.0f, 0.0f, 0.0f};
        memory.write(base + profile.modules.view_angles, view_angles, sizeof(view_angles));
        put_ref(base + profile.modules.sensitivity, 0x70000000);
        memory.put(0x70000000 + profile.modules.sensitivity_sensitivity, 2.0f);
    }
    void put_ref(std::uintptr_t address, std::uintptr_t value) { memory.put(address, value); }
};

static phantom::Frame sample_frame() {
    phantom::Frame frame{};
    frame.local.slot = 1;
    frame.local.pawn = 0x40000000;
    frame.local.name = "local";
    frame.local.team = 2;
    frame.local.health = 100;
    frame.local.armor = 100;
    frame.local.position = {0, 0, 0};
    frame.local.velocity = {0, 0, 0};
    frame.eye = {0, 0, 64};
    frame.angles = {0, 0, 0};
    const float matrix[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
    std::copy(std::begin(matrix), std::end(matrix), frame.matrix.begin());
    frame.sensitivity = 2.0f;
    frame.flags = 1;
    phantom::Actor enemy{};
    enemy.slot = 2;
    enemy.pawn = 0x41000000;
    enemy.name = "enemy";
    enemy.team = 3;
    enemy.health = 100;
    enemy.armor = 100;
    enemy.position = {100, 1, 0};
    enemy.velocity = {0, 0, 0};
    enemy.bones["head"] = {100, 1, 64};
    enemy.spotted = true;
    frame.actors = {enemy};
    frame.crosshair_pawn = enemy.pawn;
    return frame;
}

static void core_math_tests() {
    const phantom::Vec3 eye{0, 0, 0}, target{10, 0, 0};
    const auto angle = phantom::angle_to(eye, target);
    check(angle && std::fabs(angle->x) < 0.0001 && std::fabs(angle->y) < 0.0001, "angle_to horizontal target");
    const auto wrapped = phantom::angle_delta({0, -179, 0}, {0, 179, 0});
    check(std::fabs(wrapped.y - 2.0) < 0.0001, "wrapped angle delta");
    float velocity = 0.0f;
    for (int index = 0; index < 300; ++index) {
        const auto result = phantom::smooth_damp(0.0f, 10.0f, velocity, 0.15f, 90.0f, 1.0f / 60.0f);
        check(result.first >= 0.0f && result.first <= 10.0f, "smooth damp does not overshoot");
        velocity = result.second;
    }
    const float matrix[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
    auto projected = phantom::project({0, 0, 0}, phantom::Matrix16{1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1}, 1920, 1080);
    check(projected && std::fabs(projected->x - 960) < 0.001 && std::fabs(projected->y - 540) < 0.001, "identity projection centers");
    (void)matrix;
}

static void decoder_tests() {
    Fixture fixture;
    phantom::Decoder decoder(fixture.memory, fixture.base, fixture.profile);
    const auto frame = decoder.capture(phantom::Settings{});
    check(decoder.stride() == 0x70, "entity stride calibration uses unique local pawn match");
    check(frame.local.pawn == fixture.local_pawn, "local pawn decoded");
    check(frame.actors.size() == 1 && frame.actors.front().pawn == fixture.enemy_pawn, "enemy actor decoded");
    check(frame.actors.front().name == "fixture enemy", "enemy name sanitized/decoded");
    check(frame.actors.front().spotted == true, "spotted mask is local-specific");
    check(frame.actors.front().bones.at("head").z == 64.0, "head bone decoded");
    check(frame.crosshair_pawn == fixture.enemy_pawn, "crosshair entity resolved");
    fixture.memory.put(fixture.enemy_pawn + fixture.profile.fields.health, static_cast<std::int32_t>(0));
    // A dead enemy contributes no live actor, matching the Python implementation.
    phantom::Decoder decoder_dead(fixture.memory, fixture.base, fixture.profile);
    check(decoder_dead.capture(phantom::Settings{}).actors.empty(), "dead actor omitted");
    fixture.memory.put(fixture.enemy_pawn + fixture.profile.fields.health, static_cast<std::int32_t>(-100));
    phantom::Decoder decoder_invalid(fixture.memory, fixture.base, fixture.profile);
    check(decoder_invalid.capture(phantom::Settings{}).actors.empty(), "invalid enemy health omitted");
}

static void bomb_tests() {
    Fixture fixture;
    phantom::Decoder decoder(fixture.memory, fixture.base, fixture.profile);
    auto snapshot = decoder.capture_bomb();
    check(!snapshot.valid, "missing planted bomb stays unavailable");
    fixture.put_ref(fixture.base + fixture.profile.modules.planted_c4, 0x71000000);
    fixture.memory.put<std::uint8_t>(0x71000000 + fixture.profile.bomb.planted_ticking, 1);
    fixture.memory.put(0x71000000 + fixture.profile.bomb.planted_site, static_cast<std::int32_t>(1));
    fixture.memory.put(0x71000000 + fixture.profile.bomb.planted_detonation, 150.0f);
    fixture.memory.put(0x71000000 + fixture.profile.bomb.planted_timer_length, 40.0f);
    fixture.memory.put<std::uint8_t>(0x71000000 + fixture.profile.bomb.planted_being_defused, 1);
    fixture.memory.put(0x71000000 + fixture.profile.bomb.planted_defuse_remaining, 3.0f);
    fixture.memory.put(0x71000000 + fixture.profile.bomb.planted_defuse_length, 5.0f);
    fixture.memory.put<std::uint8_t>(0x71000000 + fixture.profile.bomb.planted_defused, 0);
    fixture.memory.put<std::uint8_t>(0x71000000 + fixture.profile.bomb.planted_activated, 1);
    snapshot = decoder.capture_bomb();
    check(snapshot.valid && snapshot.planted && !snapshot.defused && snapshot.defusing, "planted/defusing state captured");
    check(snapshot.site == 2 && std::fabs(snapshot.game_time - 123.5) < 0.001, "site and simulation time captured");
    check(std::fabs(snapshot.detonation_time - 150.0) < 0.001, "detonation timestamp captured");
    check(std::fabs(snapshot.defuse_end_time - 126.5) < 0.001, "remaining defuse time converted to end timestamp");
}

static void input_tests() {
    const auto frame = sample_frame();
    phantom::Settings settings;
    settings.aim = "smooth";
    phantom::AimController aim;
    bool saw_nonzero = false;
    for (int index = 0; index < 10; ++index) {
        const auto move = aim.step(frame, settings, true, 1.0f / 60.0f);
        saw_nonzero = saw_nonzero || move.first != 0 || move.second != 0;
        check(std::abs(move.first) <= 250 && std::abs(move.second) <= 250, "smooth aim remains count bounded");
    }
    check(saw_nonzero, "smooth aim emits bounded non-zero movement toward target");
    phantom::AimController hardlock;
    settings.aim = "hardlock";
    const auto hard = hardlock.step(frame, settings, true, 1.0f / 60.0f);
    check(std::abs(hard.first) <= 250 && std::abs(hard.second) <= 250, "hardlock remains count bounded");
    settings.aim = "off";
    phantom::TriggerController trigger;
    settings.trigger = true;
    check(!trigger.step(frame, settings, true, 0.0), "trigger waits for delay");
    check(trigger.step(frame, settings, true, 0.2), "trigger fires after delay");
    check(!frame.actors.front().spotted.has_value() || frame.actors.front().spotted.value(), "sample target spotted state is explicit");
}

static void run_test(const char* name, void (*test)()) {
    try {
        test();
    } catch (const std::exception& error) {
        std::fprintf(stderr, "FAIL: %s threw: %s\n", name, error.what());
        ++failures;
    }
}

int main() {
    run_test("core math", core_math_tests);
    run_test("decoder", decoder_tests);
    run_test("bomb", bomb_tests);
    run_test("input", input_tests);
    if (failures == 0) {
        std::printf("cpp game core: %u checks passed\n", checks);
        return 0;
    }
    std::fprintf(stderr, "cpp game core: %d of %u checks failed\n", failures, checks);
    return 1;
}
