#include "phantom/core.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <set>

namespace phantom {
namespace {
constexpr std::size_t max_read = 1024 * 1024;
constexpr double min_pointer = 0x10000;
constexpr double max_pointer = 0x00007fffffff0000ULL;
constexpr std::array<std::pair<const char*, const char*>, 13> bone_links{{
    {"head", "neck"}, {"neck", "chest"}, {"chest", "pelvis"},
    {"neck", "left_shoulder"}, {"left_shoulder", "left_elbow"}, {"left_elbow", "left_hand"},
    {"neck", "right_shoulder"}, {"right_shoulder", "right_elbow"}, {"right_elbow", "right_hand"},
    {"pelvis", "left_knee"}, {"left_knee", "left_foot"},
    {"pelvis", "right_knee"}, {"right_knee", "right_foot"}}};

bool finite(const Vec3& value) {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}
bool plausible_vector(const Vec3& value) {
    return finite(value) && std::abs(value.x) < 1000000 && std::abs(value.y) < 1000000 && std::abs(value.z) < 1000000;
}
std::string sanitize_name(const std::string& raw, std::uint32_t slot) {
    std::string clean;
    clean.reserve(40);
    for (unsigned char ch : raw) {
        if (ch == 0) break;
        if (std::isprint(ch)) {
            clean.push_back(static_cast<char>(ch));
            if (clean.size() == 40) break;
        }
    }
    return clean.empty() ? "player " + std::to_string(slot) : clean;
}
}

Profile Profile::reference_26598758() {
    return {{0x2709010, 0x2553d38, 0x252b0c8, 0x2559640, 0x256a4b8, 0x2551038, 0x58,
             0x25537e8, 0x24b9b90},
            {844, 999, 816, 1012, 1016, 200, 259, 3936, 320, 2348, 1788, 7936,
             7864, 12, 14092, 2352, 4872, 76, 0x3b8},
            {0x10, 512, 0x7fff, 0x80, 32, 64, {0x70, 0x78}},
            {0x8c7, 0x1288, 0x128c, 0x12b8, 0x12c0, 0x12c4, 0x12d8, 0x12d4, 0x12dc, 0x12d0},
            {0x12f0, 0x48, 0x60,
             0x10, 0x10, 0x520, 0x788,
             0x380,
             0x1288, 0x1290, 0x50,
             0x1ba, 0x1bc,
             0x1d0, 0x1d4, 0x1d8, 0x1e8,
             0x2f8,
             0x18a0, 0x18a4,
             0x18a8, 0x18ac,
             0x18b0, 0x18b4,
             0x18d8, 0x1b64, 0x208},
            "cb01076744f3554324d76b7a4830f0fcdfde95fb"};
}

double distance(const Vec3& a, const Vec3& b) {
    const double dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}
Vec3 add(const Vec3& a, const Vec3& b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }

std::optional<Vec3> project(const Vec3& point, const Matrix16& matrix, int width, int height) {
    if (width <= 0 || height <= 0 || !plausible_vector(point)) return std::nullopt;
    for (float value : matrix) if (!std::isfinite(value)) return std::nullopt;
    const double w = matrix[12] * point.x + matrix[13] * point.y + matrix[14] * point.z + matrix[15];
    if (w < 0.01) return std::nullopt;
    const double x = (matrix[0] * point.x + matrix[1] * point.y + matrix[2] * point.z + matrix[3]) / w;
    const double y = (matrix[4] * point.x + matrix[5] * point.y + matrix[6] * point.z + matrix[7]) / w;
    if (std::abs(x) > 4 || std::abs(y) > 4) return std::nullopt;
    return Vec3{static_cast<float>(width * (1.0 + x) / 2.0), static_cast<float>(height * (1.0 - y) / 2.0), 0.0f};
}

std::optional<Vec3> angle_to(const Vec3& eye, const Vec3& target) {
    const double x = target.x - eye.x, y = target.y - eye.y, z = target.z - eye.z;
    const double flat = std::hypot(x, y);
    if (flat < 0.001) return std::nullopt;
    constexpr double pi = 3.14159265358979323846;
    return Vec3{-std::atan2(z, flat) * 180.0 / pi, std::atan2(y, x) * 180.0 / pi, 0.0};
}
Vec3 angle_delta(const Vec3& target, const Vec3& current) {
    auto wrap = [](double degrees) {
        double wrapped = std::fmod(degrees + 180.0, 360.0);
        if (wrapped < 0) wrapped += 360.0;
        return wrapped - 180.0;
    };
    return {wrap(target.x - current.x), wrap(target.y - current.y), 0.0};
}

std::pair<float, float> smooth_damp(float current, float target, float velocity,
                                    float smooth_time, float max_speed, float dt) {
    if (!std::isfinite(current) || !std::isfinite(target) || !std::isfinite(velocity) ||
        !std::isfinite(smooth_time) || !std::isfinite(max_speed) || !std::isfinite(dt) || dt <= 0)
        return {current, 0.0f};
    dt = std::min(dt, 0.05f);
    const float omega = 2.0f / std::max(0.001f, smooth_time);
    const float x = omega * dt;
    const float decay = 1.0f / (1.0f + x + 0.48f * x * x + 0.235f * x * x * x);
    const float change = std::max(-max_speed * smooth_time, std::min(max_speed * smooth_time, current - target));
    const float adjusted = current - change;
    const float temp = (velocity + omega * change) * dt;
    const float next_velocity = (velocity - omega * temp) * decay;
    float output = adjusted + (change + temp) * decay;
    if ((target - current > 0) == (output > target)) return {target, 0.0f};
    return {output, next_velocity};
}

Decoder::Decoder(const IMemory& memory, std::uintptr_t base, const Profile& profile)
    : memory_(memory), base_(base), profile_(profile) {}
std::size_t Decoder::stride() const {
    if (!stride_) throw ReadError("Entity stride has not been calibrated.");
    return *stride_;
}
template<class T> T Decoder::scalar(std::uintptr_t address) const {
    T value{};
    if (!memory_.read(address, &value, sizeof(value))) throw ReadError("Unmapped memory read.");
    return value;
}
template std::uint8_t Decoder::scalar<std::uint8_t>(std::uintptr_t) const;
template std::uint32_t Decoder::scalar<std::uint32_t>(std::uintptr_t) const;
template std::int32_t Decoder::scalar<std::int32_t>(std::uintptr_t) const;
template float Decoder::scalar<float>(std::uintptr_t) const;

std::uintptr_t Decoder::pointer(std::uintptr_t address, bool nullable) const {
    const std::uintptr_t value = scalar<std::uintptr_t>(address);
    if (value == 0 && nullable) return 0;
    if (value < min_pointer || value > max_pointer || value % 8 != 0)
        throw ReadError("Invalid/null pointer; game may be loading.");
    return value;
}
Vec3 Decoder::vector(std::uintptr_t address) const {
    Vec3 value{};
    float components[3]{};
    if (!memory_.read(address, components, sizeof(components))) throw ReadError("Short memory read.");
    value = {components[0], components[1], components[2]};
    if (!plausible_vector(value)) throw ReadError("Invalid vector.");
    return value;
}
std::uintptr_t Decoder::entity(std::uintptr_t root, std::uint32_t index,
                               std::optional<std::uint32_t> stride_override) const {
    if (index > profile_.layout.handle_mask) throw ReadError("Entity index is out of range.");
    const std::uint32_t resolved_stride = stride_override.has_value()
        ? *stride_override
        : static_cast<std::uint32_t>(stride());
    const std::uintptr_t chunk = pointer(root + profile_.layout.chunk_offset +
        8ULL * (index / profile_.layout.chunk_size));
    return pointer(chunk + static_cast<std::uintptr_t>(resolved_stride) * (index % profile_.layout.chunk_size), true);
}
std::uintptr_t Decoder::handle(std::uintptr_t root, std::uint32_t handle) const {
    return handle == 0 || handle == 0xffffffffU ? 0 : entity(root, handle & profile_.layout.handle_mask);
}
void Decoder::calibrate(std::uintptr_t root, std::uintptr_t local_controller, std::uintptr_t local_pawn) {
    const std::uint32_t handle = scalar<std::uint32_t>(local_controller + profile_.fields.pawn_handle);
    std::vector<std::uint32_t> matches;
    for (std::uint32_t candidate : profile_.layout.entry_strides) {
        if (candidate == 0 || candidate % 8 != 0) continue;
        try {
            if (entity(root, handle & profile_.layout.handle_mask, candidate) == local_pawn) matches.push_back(candidate);
        } catch (const ReadError&) {}
    }
    if (matches.size() != 1) {
        stride_.reset();
        throw ReadError("Cannot uniquely calibrate entity stride against the local pawn.");
    }
    stride_ = matches.front();
}

std::map<std::string, Vec3> Decoder::bones(std::uintptr_t scene, const Vec3& position,
                                           const Settings& settings) const {
    if (settings.bones.empty()) return {};
    std::map<std::string, Vec3> result;
    try {
        const std::uintptr_t array = pointer(scene + profile_.fields.model_state + profile_.layout.bone_array);
        std::size_t count = 0;
        for (const auto& [_, index] : settings.bones) count = std::max(count, static_cast<std::size_t>(index) + 1);
        if (count > max_read / profile_.layout.bone_stride) return {};
        std::vector<std::uint8_t> data(count * profile_.layout.bone_stride);
        if (!memory_.read(array, data.data(), data.size())) return {};
        for (const auto& [name, index] : settings.bones) {
            float bone_values[3]{};
            const auto offset = static_cast<std::size_t>(index) * profile_.layout.bone_stride;
            std::memcpy(bone_values, data.data() + offset, sizeof(bone_values));
            const Vec3 bone{bone_values[0], bone_values[1], bone_values[2]};
            const double spacing = distance(bone, position);
            if (!plausible_vector(bone) || spacing <= 0.01 || spacing >= 150.0) return {};
            result.emplace(name, bone);
        }
        const auto head_it = result.find("head");
        if (head_it == result.end() || !(head_it->second.z - position.z > 25.0 && head_it->second.z - position.z < 100.0)) return {};
        return result;
    } catch (const ReadError&) {
        return {};
    }
}

Actor Decoder::actor(std::uintptr_t pawn, std::uint32_t slot, const std::string& name,
                     std::optional<std::uint32_t> local_slot, const Settings& settings, bool with_bones) {
    const std::int32_t health = scalar<std::int32_t>(pawn + profile_.fields.health);
    const std::int32_t armor = scalar<std::int32_t>(pawn + profile_.fields.armor);
    const std::uint8_t team = scalar<std::uint8_t>(pawn + profile_.fields.team);
    if (health < 0 || health > 100 || armor < 0 || armor > 100 || (team != 2 && team != 3))
        throw ReadError("Player values do not match this profile.");
    const std::uintptr_t scene = pointer(pawn + profile_.fields.scene);
    std::uint8_t dormant = 0;
    if (!memory_.read(scene + profile_.fields.dormant, &dormant, 1)) throw ReadError("Short dormant read.");
    if (dormant) throw ReadError("Dormant actor.");
    const Vec3 position = vector(scene + profile_.fields.origin);
    const Vec3 velocity = vector(pawn + profile_.fields.velocity);
    if (std::abs(velocity.x) > 10000 || std::abs(velocity.y) > 10000 || std::abs(velocity.z) > 10000)
        throw ReadError("Implausible velocity.");
    std::optional<bool> spotted;
    if (local_slot) {
        try {
            const std::uint64_t mask = scalar<std::uint64_t>(pawn + profile_.fields.spotted_state + profile_.fields.spotted_mask);
            spotted = (mask & (1ULL << ((*local_slot) - 1))) != 0;
        } catch (const ReadError&) {}
    }
    return {slot, pawn, name, team, health, armor, position, velocity,
            with_bones ? bones(scene, position, settings) : std::map<std::string, Vec3>{}, spotted};
}

Frame Decoder::capture(const Settings& settings) {
    const ProfileModules& modules = profile_.modules;
    const std::uintptr_t root = pointer(base_ + modules.entity_list);
    const std::uintptr_t local_pawn = pointer(base_ + modules.local_player_pawn);
    const std::uintptr_t local_controller = pointer(base_ + modules.local_player_controller);
    calibrate(root, local_controller, local_pawn);
    std::vector<std::pair<std::uint32_t, std::uintptr_t>> controllers;
    std::optional<std::uint32_t> local_slot;
    for (std::uint32_t slot = 1; slot <= profile_.layout.controller_limit; ++slot) {
        try {
            const std::uintptr_t controller = entity(root, slot);
            if (!controller) continue;
            if (controller == local_controller) local_slot = slot;
            controllers.emplace_back(slot, controller);
        } catch (const ReadError&) {}
    }
    if (!local_slot) throw ReadError("Local controller is absent from the entity list.");
    Actor local = actor(local_pawn, *local_slot, "local", local_slot, settings, false);
    const Vec3 view = vector(local_pawn + profile_.fields.view_offset);
    if (view.z < 0 || view.z > 100 || std::abs(view.x) > 10 || std::abs(view.y) > 10)
        throw ReadError("Invalid eye offset.");
    Matrix16 matrix{};
    if (!memory_.read(base_ + modules.view_matrix, matrix.data(), sizeof(matrix))) throw ReadError("Short view matrix read.");
    bool matrix_nonzero = false;
    for (float value : matrix) {
        if (!std::isfinite(value) || std::abs(value) >= 1e8) throw ReadError("Invalid view matrix.");
        matrix_nonzero = matrix_nonzero || std::abs(value) > 0.001f;
    }
    if (!matrix_nonzero) throw ReadError("Invalid view matrix.");
    const Vec3 angles3 = vector(base_ + modules.view_angles);
    if (angles3.x < -90 || angles3.x > 90 || std::abs(angles3.y) > 360) throw ReadError("Invalid view angles.");
    const std::uintptr_t sensitivity_address = pointer(base_ + modules.sensitivity);
    const float sensitivity = scalar<float>(sensitivity_address + modules.sensitivity_sensitivity);
    if (!std::isfinite(sensitivity) || sensitivity < 0.01f || sensitivity > 100.0f) throw ReadError("Invalid sensitivity.");
    const std::uint32_t flags = scalar<std::uint32_t>(local_pawn + profile_.fields.flags);
    std::vector<Actor> actors;
    std::vector<std::string> spectators;
    for (const auto& [slot, controller] : controllers) {
        if (controller == local_controller) continue;
        try {
            std::uint8_t raw[128]{};
            if (!memory_.read(controller + profile_.fields.name, raw, sizeof(raw))) continue;
            const std::string name = sanitize_name(reinterpret_cast<const char*>(raw), slot);
            const std::uint32_t pawn_handle = scalar<std::uint32_t>(controller + profile_.fields.pawn_handle);
            const std::uintptr_t pawn = handle(root, pawn_handle);
            std::int32_t health = 0;
            if (pawn != 0 && memory_.read(pawn + profile_.fields.health, &health, sizeof(health)) && health > 0) {
                actors.push_back(actor(pawn, slot, name, local_slot, settings, true));
                continue;
            }
            const std::uint32_t observer_handle = scalar<std::uint32_t>(controller + profile_.fields.observer_pawn);
            const std::uintptr_t observer = handle(root, observer_handle);
            if (!observer) continue;
            const std::uintptr_t services = pointer(observer + profile_.fields.observer_services);
            const std::uint32_t target_handle = scalar<std::uint32_t>(services + profile_.fields.observer_target);
            if (handle(root, target_handle) == local_pawn) spectators.push_back(name);
        } catch (const ReadError&) {}
    }
    std::optional<std::uintptr_t> crosshair;
    try {
        const std::int32_t index = scalar<std::int32_t>(local_pawn + profile_.fields.crosshair);
        if (index > 0 && static_cast<std::uint32_t>(index) <= profile_.layout.handle_mask) crosshair = entity(root, static_cast<std::uint32_t>(index));
    } catch (const ReadError&) {}
    if (pointer(base_ + modules.local_player_pawn) != local_pawn) throw ReadError("Local pawn changed during capture.");
    return {std::move(local), add(local.position, view), {angles3.x, angles3.y, 0.0}, matrix, sensitivity,
            flags, std::move(actors), crosshair, std::move(spectators)};
}

BombSnapshot Decoder::capture_bomb() const {
    const std::uintptr_t rules = [&]() -> std::uintptr_t {
        try { return pointer(base_ + profile_.modules.game_rules, true); }
        catch (const ReadError&) { return 0; }
    }();
    bool rules_planted = false;
    if (rules) {
        std::uint8_t raw = 0;
        if (!memory_.read(rules + profile_.bomb.rules_bomb_planted, &raw, 1)) throw ReadError("Short game-rules read.");
        rules_planted = raw != 0;
    }
    const auto planted = pointer(base_ + profile_.modules.planted_c4, true);
    if (!planted) return {{}, false, false, false, 0, 0.0, 0.0, 0.0};
    std::uint8_t ticking = 0, being_defused = 0, defused = 0, activated = 0;
    if (!memory_.read(planted + profile_.bomb.planted_ticking, &ticking, 1)) throw ReadError("Short bomb state read.");
    const std::int32_t raw_site = scalar<std::int32_t>(planted + profile_.bomb.planted_site);
    const float detonation = scalar<float>(planted + profile_.bomb.planted_detonation);
    const float timer_length = scalar<float>(planted + profile_.bomb.planted_timer_length);
    if (!memory_.read(planted + profile_.bomb.planted_being_defused, &being_defused, 1)) throw ReadError("Short defuse state read.");
    const float defuse_remaining = scalar<float>(planted + profile_.bomb.planted_defuse_remaining);
    const float defuse_length = scalar<float>(planted + profile_.bomb.planted_defuse_length);
    if (!memory_.read(planted + profile_.bomb.planted_defused, &defused, 1)) throw ReadError("Short defused state read.");
    if (!memory_.read(planted + profile_.bomb.planted_activated, &activated, 1)) throw ReadError("Short activation state read.");
    const std::uintptr_t local_pawn = pointer(base_ + profile_.modules.local_player_pawn);
    const float game_time = scalar<float>(local_pawn + profile_.fields.simulation_time);
    if (!std::isfinite(game_time) || game_time < 0 || !std::isfinite(detonation) || detonation < 0 ||
        !std::isfinite(timer_length) || timer_length < 0 || !std::isfinite(defuse_remaining) || defuse_remaining < 0 ||
        !std::isfinite(defuse_length) || defuse_length < 0)
        throw ReadError("Invalid planted-bomb data.");
    const bool planted_now = rules_planted || activated != 0 || ticking != 0;
    const std::uint32_t site = raw_site == 0 ? 1 : raw_site == 1 ? 2 : 0;
    BombSnapshot snapshot{};
    snapshot.valid = true;
    snapshot.planted = planted_now;
    snapshot.defused = defused != 0;
    snapshot.defusing = being_defused != 0;
    snapshot.site = site;
    snapshot.game_time = game_time;
    snapshot.detonation_time = detonation;
    snapshot.defuse_end_time = snapshot.defusing ? game_time + defuse_remaining : 0.0;
    return snapshot;
}

std::optional<Target> choose_target(const Frame& frame, const Settings& settings) {
    if (frame.local.health <= 0) return std::nullopt;
    std::optional<Target> best;
    double best_score = settings.aim_fov;
    for (const Actor& actor : frame.actors) {
        if (actor.team == frame.local.team || actor.health <= 0 || actor.spotted != true) continue;
        if (distance(actor.position, frame.local.position) * 0.0254 > settings.max_distance_m) continue;
        const auto bone = actor.bones.find(settings.priority_bone);
        if (bone == actor.bones.end()) continue;
        const Vec3 predicted{bone->second.x + actor.velocity.x * settings.prediction_ms / 1000.0,
                             bone->second.y + actor.velocity.y * settings.prediction_ms / 1000.0,
                             bone->second.z + actor.velocity.z * settings.prediction_ms / 1000.0};
        const auto angle = angle_to(frame.eye, predicted);
        if (!angle) continue;
        const Vec3 delta = angle_delta(*angle, frame.angles);
        const double score = std::hypot(delta.x, delta.y);
        if (score < best_score) {
            best_score = score;
            best = Target{actor.pawn, delta};
        }
    }
    return best;
}

AimController::AimController() { reset(); }
void AimController::reset() {
    target_.reset();
    velocity_ = {};
    remainder_ = {};
}
std::optional<std::uintptr_t> AimController::target() const { return target_; }
std::pair<int, int> AimController::step(const Frame& frame, const Settings& settings, bool held, float dt) {
    const auto target = held && settings.aim != "off" ? choose_target(frame, settings) : std::nullopt;
    if (!target || !(dt > 0 && dt <= 0.1f)) {
        reset();
        return {0, 0};
    }
    if (target->pawn != target_) {
        reset();
        target_ = target->pawn;
    }
    std::array<float, 2> movement{};
    if (settings.aim == "smooth") {
        for (int index = 0; index < 2; ++index) {
            const float value = index == 0 ? static_cast<float>(target->delta.x) : static_cast<float>(target->delta.y);
            auto [position, velocity] = smooth_damp(0, value, velocity_[index], settings.smooth_time, settings.max_aim_speed, dt);
            remainder_[index] += 0; // retained for layout stability; no hidden input accumulation.
            movement[index] = position;
            velocity_[index] = velocity;
        }
    } else {
        const float cap = settings.max_aim_speed * dt;
        movement = {std::max(-cap, std::min(cap, static_cast<float>(target->delta.x))),
                    std::max(-cap, std::min(cap, static_cast<float>(target->delta.y)))};
    }
    const std::array<double, 2> counts{
        -static_cast<double>(movement[1]) / (frame.sensitivity * settings.mouse_yaw),
         static_cast<double>(movement[0]) / (frame.sensitivity * settings.mouse_pitch)};
    std::array<int, 2> result{};
    for (std::size_t index = 0; index < counts.size(); ++index) {
        const double value = std::max(-250.0, std::min(250.0, counts[index] + remainder_[index]));
        const double truncated = std::trunc(value);
        remainder_[index] = static_cast<float>(value - truncated);
        result[index] = static_cast<int>(truncated);
    }
    return {result[0], result[1]};
}

TriggerController::TriggerController() { reset(); }
void TriggerController::reset() {
    target_.reset();
    since_.reset();
}
bool TriggerController::step(const Frame& frame, const Settings& settings, bool held, double now) {
    const Actor* target = nullptr;
    for (const Actor& actor : frame.actors) {
        if (frame.crosshair_pawn && actor.pawn == *frame.crosshair_pawn && actor.health > 0 &&
            actor.team != frame.local.team && actor.spotted == true) {
            target = &actor;
            break;
        }
    }
    if (!settings.trigger || !held || frame.local.health <= 0 || !target) {
        reset();
        return false;
    }
    if (target_ != target->pawn) {
        target_ = target->pawn;
        since_ = now;
    }
    if (since_ && now - *since_ >= settings.trigger_delay_ms / 1000.0) {
        since_ = now;
        return true;
    }
    return false;
}

bool JumpController::step(const Frame& frame, const Settings& settings, bool held) {
    const bool ground = (frame.flags & 1u) != 0;
    const bool fire = settings.bunny_hop && held && frame.local.health > 0 && ground && !grounded_;
    grounded_ = held ? ground : false;
    return fire;
}

} // namespace phantom
