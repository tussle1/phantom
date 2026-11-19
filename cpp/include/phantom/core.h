#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace phantom {

struct Vec3 { double x = 0, y = 0, z = 0; };
using Matrix16 = std::array<float, 16>;
using BoneMap = std::map<std::string, int>;
struct ReadError : std::runtime_error { using std::runtime_error::runtime_error; };

class IMemory {
public:
    virtual ~IMemory() = default;
    virtual bool read(std::uintptr_t address, void* output, std::size_t size) const = 0;
};

// Explicit opt-in read/write interface used only by the local cosmetic adapter.
class IProcessMemory : public IMemory {
public:
    virtual bool write(std::uintptr_t address, const void* input, std::size_t size) = 0;
};

struct ProfileModules {
    std::uintptr_t entity_list = 0, local_player_pawn = 0, local_player_controller = 0;
    std::uintptr_t view_matrix = 0, view_angles = 0, sensitivity = 0, sensitivity_sensitivity = 0;
    // Public build-specific offsets used only by the optional internal adapter.
    std::uintptr_t game_rules = 0, planted_c4 = 0;
};
struct ProfileFields {
    std::uint32_t health = 0, team = 0, scene = 0, flags = 0, velocity = 0, origin = 0;
    std::uint32_t dormant = 0, view_offset = 0, model_state = 0, pawn_handle = 0, name = 0;
    std::uint32_t armor = 0, spotted_state = 0, spotted_mask = 0, crosshair = 0;
    std::uint32_t observer_pawn = 0, observer_services = 0, observer_target = 0;
    std::uint32_t simulation_time = 0;
};
struct ProfileLayout {
    std::uint32_t chunk_offset = 0, chunk_size = 0, handle_mask = 0, bone_array = 0;
    std::uint32_t bone_stride = 0, controller_limit = 0;
    std::vector<std::uint32_t> entry_strides;
};
struct BombFieldLayout {
    std::uint32_t rules_bomb_planted = 0;
    std::uint32_t planted_ticking = 0, planted_site = 0, planted_detonation = 0;
    std::uint32_t planted_timer_length = 0, planted_being_defused = 0;
    std::uint32_t planted_defuse_remaining = 0, planted_defuse_length = 0, planted_defused = 0;
    std::uint32_t planted_activated = 0;
};
struct SkinFieldLayout {
    std::uint32_t weapon_services = 0, my_weapons = 0, active_weapon = 0;
    std::uint32_t entity_identity = 0, identity_handle = 0, owner_entity = 0, steam_id = 0;
    std::uint32_t subclass_id = 0;
    std::uint32_t attributes_initialized = 0, attribute_manager = 0, econ_item = 0;
    std::uint32_t item_definition_index = 0, entity_quality = 0;
    std::uint32_t item_id_high = 0, item_id_low = 0, account_id = 0, item_initialized = 0;
    std::uint32_t custom_name = 0;
    std::uint32_t original_owner_xuid_low = 0, original_owner_xuid_high = 0;
    std::uint32_t fallback_paint_kit = 0, fallback_seed = 0;
    std::uint32_t fallback_wear = 0, fallback_stattrak = 0;
    std::uint32_t viewmodel_attachment = 0, custom_econ_reload_id = 0, mesh_group_mask = 0;
};
// engine2.dll locations used by the optional skin runtime to force a network
// full update (delta tick) after a loadout change so writes become visible.
struct Engine2Layout {
    std::uintptr_t network_game_client = 0; // RVA of the global interface pointer.
    std::uint32_t delta_tick = 0;           // m_nDeltaTick within INetworkGameClient.
};
struct Profile {
    ProfileModules modules;
    ProfileFields fields;
    ProfileLayout layout;
    BombFieldLayout bomb;
    SkinFieldLayout skins;
    Engine2Layout engine2;
    std::string source;
    static Profile reference_26598758();
};

struct EspStyle {
    std::string visible_color = "#55dc8c", hidden_color = "#ffad50", team_color = "#66b9ff";
    std::string health_color = "#55dc8c", armor_color = "#66b9ff";
    int line_width = 1;
    bool box = false, names = true, distance = true;
};
struct Settings {
    EspStyle esp_style{};
    bool esp = true, skeleton = true, health = true, armor = true, teammates = false;
    std::string aim = "off";
    float aim_fov = 3.0f, smooth_time = 0.12f, max_aim_speed = 90.0f;
    float prediction_ms = 0.0f, trigger_delay_ms = 150.0f, max_distance_m = 150.0f;
    float mouse_yaw = 0.022f, mouse_pitch = 0.022f;
    bool trigger = false, bunny_hop = false;
    std::string priority_bone = "head";
    BoneMap bones = {{"head", 6}, {"neck", 5}, {"chest", 4}, {"pelvis", 0},
                     {"left_shoulder", 8}, {"left_elbow", 9}, {"left_hand", 10},
                     {"right_shoulder", 13}, {"right_elbow", 14}, {"right_hand", 15},
                     {"left_knee", 23}, {"left_foot", 24}, {"right_knee", 26}, {"right_foot", 27}};
};

struct Actor {
    std::uint32_t slot = 0;
    std::uintptr_t pawn = 0;
    std::string name;
    int team = 0, health = 0, armor = 0;
    Vec3 position{}, velocity{};
    std::map<std::string, Vec3> bones;
    std::optional<bool> spotted;
};
struct Frame {
    Actor local;
    Vec3 eye{}, angles{};
    Matrix16 matrix{};
    float sensitivity = 0;
    std::uint32_t flags = 0;
    std::vector<Actor> actors;
    std::optional<std::uintptr_t> crosshair_pawn;
    std::vector<std::string> spectators;
};
struct BombSnapshot {
    bool valid = false;
    bool planted = false;
    bool defused = false;
    bool defusing = false;
    std::uint32_t site = 0; // 0 unknown, 1 A, 2 B
    double game_time = 0, detonation_time = 0, defuse_end_time = 0;
};

double distance(const Vec3& a, const Vec3& b);
Vec3 add(const Vec3& a, const Vec3& b);
std::optional<Vec3> project(const Vec3& point, const Matrix16& matrix, int width, int height);
std::optional<Vec3> angle_to(const Vec3& eye, const Vec3& target);
Vec3 angle_delta(const Vec3& target, const Vec3& current);
std::pair<float, float> smooth_damp(float current, float target, float velocity,
                                    float smooth_time, float max_speed, float dt);

class Decoder {
public:
    Decoder(const IMemory& memory, std::uintptr_t base, const Profile& profile);
    std::size_t stride() const;
    std::uintptr_t entity(std::uintptr_t root, std::uint32_t index,
                          std::optional<std::uint32_t> stride_override = std::nullopt) const;
    std::uintptr_t handle(std::uintptr_t root, std::uint32_t handle) const;
    void calibrate(std::uintptr_t root, std::uintptr_t local_controller, std::uintptr_t local_pawn);
    Frame capture(const Settings& settings);
    BombSnapshot capture_bomb() const;

private:
    template<class T> T scalar(std::uintptr_t address) const;
    std::uintptr_t pointer(std::uintptr_t address, bool nullable = false) const;
    Vec3 vector(std::uintptr_t address) const;
    Actor actor(std::uintptr_t pawn, std::uint32_t slot, const std::string& name,
                std::optional<std::uint32_t> local_slot, const Settings& settings,
                bool with_bones = true);
    std::map<std::string, Vec3> bones(std::uintptr_t scene, const Vec3& position,
                                      const Settings& settings) const;

    const IMemory& memory_;
    std::uintptr_t base_;
    Profile profile_;
    std::optional<std::uint32_t> stride_;
};

struct Target {
    std::uintptr_t pawn = 0;
    Vec3 delta{};
};
std::optional<Target> choose_target(const Frame& frame, const Settings& settings);

class AimController {
public:
    AimController();
    void reset();
    std::pair<int, int> step(const Frame& frame, const Settings& settings, bool held, float dt);
    std::optional<std::uintptr_t> target() const;
private:
    std::optional<std::uintptr_t> target_;
    std::array<float, 2> velocity_{};
    std::array<float, 2> remainder_{};
};

class TriggerController {
public:
    TriggerController();
    void reset();
    bool step(const Frame& frame, const Settings& settings, bool held, double now);
private:
    std::optional<std::uintptr_t> target_;
    std::optional<double> since_;
};

class JumpController {
public:
    bool step(const Frame& frame, const Settings& settings, bool held);
private:
    bool grounded_ = false;
};

} // namespace phantom
