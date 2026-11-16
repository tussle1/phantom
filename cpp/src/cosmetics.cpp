#include "phantom/cosmetics.h"
#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <set>

namespace phantom {
namespace {
constexpr std::uintptr_t min_pointer = 0x10000;
constexpr std::uintptr_t max_pointer = 0x00007fffffff0000ULL;
constexpr std::size_t max_loadout_bytes = 65536;
constexpr std::size_t max_weapons_vector = 64;
constexpr std::size_t max_custom_name_len = 32;
constexpr std::uint32_t fallback_item_id_high = 0xffffffffu;
constexpr std::int32_t stattrak_quality = 9;

bool valid_values(const CosmeticValues& value) {
    return value.paint_kit <= 0x7fffffffu && value.seed <= 1000 &&
           std::isfinite(value.wear) && value.wear >= 0.0f && value.wear <= 1.0f &&
           value.stattrak >= -1 && value.stattrak <= 999999;
}
bool values_equal(const CosmeticValues& a, const CosmeticValues& b) {
    return a.paint_kit == b.paint_kit && a.seed == b.seed &&
           a.stattrak == b.stattrak && std::fabs(a.wear - b.wear) <= 1e-6f;
}
bool extras_equal(const CosmeticExtras& a, const CosmeticExtras& b) {
    return a.custom_name == b.custom_name && a.mesh_group_mask == b.mesh_group_mask;
}
bool matching(const CosmeticItem& item, std::uint64_t identity, std::uint32_t definition) {
    return item.identity == identity && item.owned_local && item.weapon_definition == definition;
}

template<class T>
bool read_scalar(const IMemory& memory, std::uintptr_t address, T& out) {
    return address >= min_pointer && address <= max_pointer &&
           memory.read(address, &out, sizeof(T));
}

template<class T>
bool write_scalar(IProcessMemory& memory, std::uintptr_t address, const T& value) {
    return address >= min_pointer && address <= max_pointer &&
           memory.write(address, &value, sizeof(T));
}

bool read_pointer(const IMemory& memory, std::uintptr_t address, std::uintptr_t& out, bool nullable = false) {
    std::uintptr_t value = 0;
    if (!read_scalar(memory, address, value)) return false;
    if (value == 0) {
        out = 0;
        return nullable;
    }
    if (value < min_pointer || value > max_pointer || (value % 8) != 0) return false;
    out = value;
    return true;
}

// Strict zero-dependency JSON parser tailored to .skin-loadout.json.
class JsonCursor {
public:
    explicit JsonCursor(const std::string& text) : text_(text) {}

    void skip_ws() {
        while (pos_ < text_.size() &&
               (text_[pos_] == ' ' || text_[pos_] == '\t' || text_[pos_] == '\n' || text_[pos_] == '\r')) {
            ++pos_;
        }
    }
    bool eof() {
        skip_ws();
        return pos_ == text_.size();
    }
    bool consume(char ch) {
        skip_ws();
        if (pos_ < text_.size() && text_[pos_] == ch) {
            ++pos_;
            return true;
        }
        return false;
    }
    bool peek(char ch) {
        skip_ws();
        return pos_ < text_.size() && text_[pos_] == ch;
    }
    bool parse_string(std::string& out) {
        skip_ws();
        if (pos_ >= text_.size() || text_[pos_] != '"') return false;
        ++pos_;
        out.clear();
        while (pos_ < text_.size()) {
            const char ch = text_[pos_++];
            if (ch == '"') return true;
            if (static_cast<unsigned char>(ch) < 0x20) return false;
            if (ch == '\\') {
                if (pos_ >= text_.size()) return false;
                const char esc = text_[pos_++];
                switch (esc) {
                    case '"': out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'n': out.push_back('\n'); break;
                    case 'r': out.push_back('\r'); break;
                    case 't': out.push_back('\t'); break;
                    default: return false;
                }
            } else {
                out.push_back(ch);
            }
            if (out.size() > 1024) return false;
        }
        return false;
    }
    bool parse_bool(bool& out) {
        skip_ws();
        if (text_.compare(pos_, 4, "true") == 0) {
            pos_ += 4;
            out = true;
            return true;
        }
        if (text_.compare(pos_, 5, "false") == 0) {
            pos_ += 5;
            out = false;
            return true;
        }
        return false;
    }
    bool parse_int64(std::int64_t& out) {
        skip_ws();
        if (pos_ >= text_.size()) return false;
        const std::size_t start = pos_;
        if (text_[pos_] == '-') ++pos_;
        if (pos_ >= text_.size() || !std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
        if (text_[pos_] == '0') {
            ++pos_;
            if (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
        } else {
            while (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
        }
        if (pos_ < text_.size() && (text_[pos_] == '.' || text_[pos_] == 'e' || text_[pos_] == 'E')) return false;
        const std::string token = text_.substr(start, pos_ - start);
        char* end = nullptr;
        errno = 0;
        const long long parsed = std::strtoll(token.c_str(), &end, 10);
        if (errno != 0 || !end || *end != '\0') return false;
        out = static_cast<std::int64_t>(parsed);
        return true;
    }
    bool parse_double(double& out) {
        skip_ws();
        if (pos_ >= text_.size()) return false;
        const std::size_t start = pos_;
        if (text_[pos_] == '-') ++pos_;
        if (pos_ >= text_.size() || !std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
        if (text_[pos_] == '0') {
            ++pos_;
            if (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
        } else {
            while (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
        }
        if (pos_ < text_.size() && text_[pos_] == '.') {
            ++pos_;
            if (pos_ >= text_.size() || !std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
            while (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
        }
        if (pos_ < text_.size() && (text_[pos_] == 'e' || text_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < text_.size() && (text_[pos_] == '+' || text_[pos_] == '-')) ++pos_;
            if (pos_ >= text_.size() || !std::isdigit(static_cast<unsigned char>(text_[pos_]))) return false;
            while (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
        }
        const std::string token = text_.substr(start, pos_ - start);
        char* end = nullptr;
        errno = 0;
        const double parsed = std::strtod(token.c_str(), &end);
        if (errno != 0 || !end || *end != '\0' || !std::isfinite(parsed)) return false;
        out = parsed;
        return true;
    }

private:
    const std::string& text_;
    std::size_t pos_ = 0;
};

bool parse_entry_object(JsonCursor& cursor, CosmeticPreferenceEntry& out) {
    if (!cursor.consume('{')) return false;
    bool has_weapon = false, has_kit = false, has_seed = false, has_wear = false;
    bool has_stattrak = false, has_name = false, has_mesh = false;
    CosmeticPreferenceEntry parsed{};
    parsed.preference.struct_size = sizeof(PhantomCosmeticPreference);
    parsed.preference.stattrak = -1;
    parsed.extras.mesh_group_mask = 0;

    if (cursor.peek('}')) return false;
    for (;;) {
        std::string key;
        if (!cursor.parse_string(key) || !cursor.consume(':')) return false;
        if (key == "weapon_definition") {
            std::int64_t val = 0;
            if (has_weapon || !cursor.parse_int64(val) || val < 1 || val > 65535) return false;
            parsed.preference.weapon_definition = static_cast<std::uint32_t>(val);
            has_weapon = true;
        } else if (key == "paint_kit") {
            std::int64_t val = 0;
            if (has_kit || !cursor.parse_int64(val) || val < 0 || val > 0x7fffffffLL) return false;
            parsed.preference.paint_kit = static_cast<std::uint32_t>(val);
            has_kit = true;
        } else if (key == "seed") {
            std::int64_t val = 0;
            if (has_seed || !cursor.parse_int64(val) || val < 0 || val > 1000) return false;
            parsed.preference.seed = static_cast<std::uint32_t>(val);
            has_seed = true;
        } else if (key == "wear") {
            double val = 0.0;
            if (has_wear || !cursor.parse_double(val) || val < 0.0 || val > 1.0) return false;
            parsed.preference.wear = static_cast<float>(val);
            has_wear = true;
        } else if (key == "stattrak") {
            std::int64_t val = 0;
            if (has_stattrak || !cursor.parse_int64(val) || val < -1 || val > 999999) return false;
            parsed.preference.stattrak = static_cast<std::int32_t>(val);
            has_stattrak = true;
        } else if (key == "custom_name") {
            std::string val;
            if (has_name || !cursor.parse_string(val) || !valid_custom_name(val)) return false;
            parsed.extras.custom_name = std::move(val);
            has_name = true;
        } else if (key == "mesh_group") {
            std::int64_t val = 0;
            if (has_mesh || !cursor.parse_int64(val) || val < 0 || !valid_mesh_group(static_cast<std::uint64_t>(val)))
                return false;
            parsed.extras.mesh_group_mask = static_cast<std::uint64_t>(val);
            has_mesh = true;
        } else {
            return false;
        }
        if (cursor.consume('}')) break;
        if (!cursor.consume(',')) return false;
    }
    if (!has_weapon || !has_kit || !has_seed || !has_wear || !has_stattrak) return false;
    out = std::move(parsed);
    return true;
}
} // namespace

bool valid_custom_name(const std::string& name) {
    if (name.size() > max_custom_name_len) return false;
    for (unsigned char ch : name) {
        if (ch < 0x20 || ch > 0x7e) return false;
    }
    return true;
}

bool valid_mesh_group(std::uint64_t mask) {
    return mask == 0 || mask == 1 || mask == 2;
}

bool parse_skin_loadout_json(const std::string& text, bool& enabled_out,
                             std::vector<CosmeticPreferenceEntry>& entries_out) {
    if (text.empty() || text.size() > max_loadout_bytes) return false;
    JsonCursor cursor(text);
    if (!cursor.consume('{')) return false;
    bool has_version = false, has_enabled = false, has_entries = false;
    bool parsed_enabled = false;
    std::vector<CosmeticPreferenceEntry> parsed_entries;
    std::set<std::uint32_t> seen_weapons;

    if (cursor.peek('}')) return false;
    for (;;) {
        std::string key;
        if (!cursor.parse_string(key) || !cursor.consume(':')) return false;
        if (key == "version") {
            std::int64_t version = 0;
            if (has_version || !cursor.parse_int64(version) || version != 1) return false;
            has_version = true;
        } else if (key == "enabled") {
            if (has_enabled || !cursor.parse_bool(parsed_enabled)) return false;
            has_enabled = true;
        } else if (key == "entries") {
            if (has_entries || !cursor.consume('[')) return false;
            if (!cursor.consume(']')) {
                for (;;) {
                    if (parsed_entries.size() >= 32) return false;
                    CosmeticPreferenceEntry entry{};
                    if (!parse_entry_object(cursor, entry)) return false;
                    if (!seen_weapons.insert(entry.preference.weapon_definition).second) return false;
                    parsed_entries.push_back(std::move(entry));
                    if (cursor.consume(']')) break;
                    if (!cursor.consume(',')) return false;
                }
            }
            has_entries = true;
        } else {
            return false;
        }
        if (cursor.consume('}')) break;
        if (!cursor.consume(',')) return false;
    }
    if (!has_version || !has_enabled || !has_entries || !cursor.eof()) return false;
    enabled_out = parsed_enabled;
    entries_out = std::move(parsed_entries);
    return true;
}

MemoryCosmeticAdapter::MemoryCosmeticAdapter(IProcessMemory& memory, std::uintptr_t client_base,
                                             const Profile& profile, MaterialRefreshFn material_refresh)
    : memory_(memory), base_(client_base), profile_(profile),
      material_refresh_(std::move(material_refresh)) {}

std::uintptr_t MemoryCosmeticAdapter::resolve_entity(std::uintptr_t root, std::uint32_t index,
                                                     std::uint32_t stride) const {
    if (index > profile_.layout.handle_mask || !profile_.layout.chunk_size) return 0;
    std::uintptr_t chunk = 0;
    if (!read_pointer(memory_, root + profile_.layout.chunk_offset +
                      8ULL * (index / profile_.layout.chunk_size), chunk)) {
        return 0;
    }
    std::uintptr_t entity = 0;
    if (!read_pointer(memory_, chunk + static_cast<std::uintptr_t>(stride) *
                      (index % profile_.layout.chunk_size), entity, true)) {
        return 0;
    }
    return entity;
}

std::uintptr_t MemoryCosmeticAdapter::resolve_handle_with_serial(std::uintptr_t root,
                                                                 std::uint32_t handle,
                                                                 std::uint32_t stride) const {
    if (handle == 0 || handle == 0xffffffffu || !profile_.layout.chunk_size) return 0;
    const std::uint32_t index = handle & profile_.layout.handle_mask;
    std::uintptr_t chunk = 0;
    if (!read_pointer(memory_, root + profile_.layout.chunk_offset +
                      8ULL * (index / profile_.layout.chunk_size), chunk)) {
        return 0;
    }
    const std::uintptr_t entry_addr = chunk + static_cast<std::uintptr_t>(stride) *
                                      (index % profile_.layout.chunk_size);
    std::uintptr_t entity = 0;
    if (!read_pointer(memory_, entry_addr, entity)) return 0;
    std::uint32_t entry_handle = 0;
    if (!read_scalar(memory_, entry_addr + profile_.skins.identity_handle, entry_handle) ||
        entry_handle != handle) {
        return 0;
    }
    // If CEntityInstance::m_pEntity is populated, cross-check its identity handle too.
    std::uintptr_t identity_ptr = 0;
    if (read_pointer(memory_, entity + profile_.skins.entity_identity, identity_ptr, true) && identity_ptr) {
        std::uint32_t instance_handle = 0;
        if (!read_scalar(memory_, identity_ptr + profile_.skins.identity_handle, instance_handle) ||
            instance_handle != handle) {
            return 0;
        }
    }
    return entity;
}

bool MemoryCosmeticAdapter::resolve_context(LocalContext& ctx) const {
    ctx = {};
    if (!base_) return false;
    if (!read_pointer(memory_, base_ + profile_.modules.entity_list, ctx.root)) return false;
    if (!read_pointer(memory_, base_ + profile_.modules.local_player_pawn, ctx.local_pawn)) return false;
    if (!read_pointer(memory_, base_ + profile_.modules.local_player_controller, ctx.local_controller)) return false;

    std::uint32_t local_pawn_handle = 0;
    if (!read_scalar(memory_, ctx.local_controller + profile_.fields.pawn_handle, local_pawn_handle)) return false;
    std::vector<std::uint32_t> matches;
    for (std::uint32_t candidate : profile_.layout.entry_strides) {
        if (candidate == 0 || (candidate % 8) != 0) continue;
        if (resolve_entity(ctx.root, local_pawn_handle & profile_.layout.handle_mask, candidate) == ctx.local_pawn) {
            matches.push_back(candidate);
        }
    }
    if (matches.size() != 1) return false;
    ctx.stride = matches.front();

    std::uint64_t steam_id = 0;
    if (read_scalar(memory_, ctx.local_controller + profile_.skins.steam_id, steam_id)) {
        ctx.local_account_id = static_cast<std::uint32_t>(steam_id & 0xffffffffULL);
    }

    std::uintptr_t weapon_services = 0;
    if (!read_pointer(memory_, ctx.local_pawn + profile_.skins.weapon_services, weapon_services)) return false;

    std::int32_t count = 0;
    if (!read_scalar(memory_, weapon_services + profile_.skins.my_weapons, count)) return false;
    if (count < 0 || static_cast<std::size_t>(count) > max_weapons_vector) return false;
    if (count > 0) {
        std::uintptr_t data = 0;
        if (!read_pointer(memory_, weapon_services + profile_.skins.my_weapons + 8, data)) return false;
        std::vector<std::uint32_t> handles(static_cast<std::size_t>(count), 0);
        if (!memory_.read(data, handles.data(), handles.size() * sizeof(std::uint32_t))) return false;
        for (std::uint32_t h : handles) {
            if (h != 0 && h != 0xffffffffu &&
                std::find(ctx.owned_handles.begin(), ctx.owned_handles.end(), h) == ctx.owned_handles.end()) {
                ctx.owned_handles.push_back(h);
            }
        }
    }
    std::uint32_t active = 0;
    if (read_scalar(memory_, weapon_services + profile_.skins.active_weapon, active) &&
        active != 0 && active != 0xffffffffu &&
        std::find(ctx.owned_handles.begin(), ctx.owned_handles.end(), active) == ctx.owned_handles.end()) {
        ctx.owned_handles.push_back(active);
    }
    return true;
}

bool MemoryCosmeticAdapter::resolve_weapon(const LocalContext& ctx, std::uint64_t identity,
                                           std::uintptr_t& weapon_out, bool& owned_local_out) const {
    weapon_out = 0;
    owned_local_out = false;
    if (identity == 0 || identity > 0xffffffffULL) return false;
    const std::uint32_t handle = static_cast<std::uint32_t>(identity);
    const std::uintptr_t weapon = resolve_handle_with_serial(ctx.root, handle, ctx.stride);
    if (!weapon) return false;

    const bool in_inventory = std::find(ctx.owned_handles.begin(), ctx.owned_handles.end(), handle) !=
                              ctx.owned_handles.end();
    std::uint32_t owner_handle = 0;
    bool owner_matches = false;
    if (read_scalar(memory_, weapon + profile_.skins.owner_entity, owner_handle) &&
        owner_handle != 0 && owner_handle != 0xffffffffu) {
        owner_matches = resolve_entity(ctx.root, owner_handle & profile_.layout.handle_mask, ctx.stride) ==
                        ctx.local_pawn;
    }
    weapon_out = weapon;
    owned_local_out = in_inventory && owner_matches;
    return true;
}

bool MemoryCosmeticAdapter::read_mesh_group(std::uintptr_t entity_ptr, std::uint64_t& mask_out) const {
    std::uintptr_t scene = 0;
    if (!read_pointer(memory_, entity_ptr + profile_.fields.scene, scene)) return false;
    return read_scalar(memory_, scene + profile_.fields.model_state + profile_.skins.mesh_group_mask, mask_out);
}

bool MemoryCosmeticAdapter::write_mesh_group(std::uintptr_t entity_ptr, std::uint64_t mask) {
    std::uintptr_t scene = 0;
    if (!read_pointer(memory_, entity_ptr + profile_.fields.scene, scene)) return false;
    return write_scalar(memory_, scene + profile_.fields.model_state + profile_.skins.mesh_group_mask, mask);
}

bool MemoryCosmeticAdapter::enumerate_local_weapons(std::vector<CosmeticItem>& out) {
    out.clear();
    LocalContext ctx{};
    if (!resolve_context(ctx)) return false;
    for (std::uint32_t handle : ctx.owned_handles) {
        CosmeticItem item{};
        if (read(static_cast<std::uint64_t>(handle), item) && item.owned_local &&
            item.weapon_definition > 0 && item.weapon_definition <= 65535) {
            out.push_back(item);
        }
    }
    return true;
}

bool MemoryCosmeticAdapter::read(std::uint64_t identity, CosmeticItem& item) {
    item = {};
    LocalContext ctx{};
    if (!resolve_context(ctx)) return false;
    std::uintptr_t weapon = 0;
    bool owned = false;
    if (!resolve_weapon(ctx, identity, weapon, owned)) return false;

    const std::uintptr_t item_view = weapon + profile_.skins.attribute_manager + profile_.skins.econ_item;
    std::uint16_t def_index = 0;
    if (!read_scalar(memory_, item_view + profile_.skins.item_definition_index, def_index) || def_index == 0)
        return false;

    std::int32_t raw_kit = 0, raw_seed = 0, raw_stattrak = -1;
    float raw_wear = 0.0f;
    if (!read_scalar(memory_, weapon + profile_.skins.fallback_paint_kit, raw_kit)) return false;
    if (!read_scalar(memory_, weapon + profile_.skins.fallback_seed, raw_seed)) return false;
    if (!read_scalar(memory_, weapon + profile_.skins.fallback_wear, raw_wear)) return false;
    if (!read_scalar(memory_, weapon + profile_.skins.fallback_stattrak, raw_stattrak)) return false;
    if (!std::isfinite(raw_wear) || raw_wear < 0.0f || raw_wear > 1.0f) return false;
    if (raw_stattrak < -1 || raw_stattrak > 999999) return false;

    const std::uint32_t kit = raw_kit < 0 ? 0u : static_cast<std::uint32_t>(raw_kit);
    const std::uint32_t seed = raw_seed < 0 ? 0u : static_cast<std::uint32_t>(raw_seed);
    if (kit > 0x7fffffffu || seed > 1000u) return false;

    if (owned && originals_.find(identity) == originals_.end() && originals_.size() < 64) {
        OriginalMeta meta{};
        meta.raw_paint_kit = raw_kit;
        meta.raw_seed = raw_seed;
        meta.raw_wear = raw_wear;
        meta.raw_stattrak = raw_stattrak;
        read_scalar(memory_, item_view + profile_.skins.item_id_high, meta.item_id_high);
        read_scalar(memory_, item_view + profile_.skins.account_id, meta.account_id);
        read_scalar(memory_, item_view + profile_.skins.entity_quality, meta.entity_quality);
        meta.has_custom_name = memory_.read(item_view + profile_.skins.custom_name,
                                            meta.original_name.data(), meta.original_name.size());
        meta.original_name.back() = '\0';
        meta.has_weapon_mesh = read_mesh_group(weapon, meta.weapon_mesh_group);
        std::uint32_t vm_handle = 0;
        if (read_scalar(memory_, weapon + profile_.skins.viewmodel_attachment, vm_handle)) {
            const std::uintptr_t vm = resolve_handle_with_serial(ctx.root, vm_handle, ctx.stride);
            if (vm) meta.has_viewmodel_mesh = read_mesh_group(vm, meta.viewmodel_mesh_group);
        }
        originals_.emplace(identity, meta);
    }

    item.identity = identity;
    item.weapon_definition = def_index;
    item.owned_local = owned;
    item.values = {kit, seed, raw_wear, raw_stattrak};
    return true;
}

void MemoryCosmeticAdapter::set_pending_extras(std::uint64_t identity, const CosmeticExtras& extras) {
    pending_[identity] = {true, extras};
}

void MemoryCosmeticAdapter::clear_pending_extras(std::uint64_t identity) {
    pending_[identity] = {false, {}};
}

bool MemoryCosmeticAdapter::write(std::uint64_t identity, const CosmeticValues& values) {
    if (!valid_values(values)) return false;
    LocalContext ctx{};
    if (!resolve_context(ctx)) return false;
    std::uintptr_t weapon = 0;
    bool owned = false;
    if (!resolve_weapon(ctx, identity, weapon, owned) || !owned) return false;

    const std::uintptr_t item_view = weapon + profile_.skins.attribute_manager + profile_.skins.econ_item;
    const auto mode_it = pending_.find(identity);
    const bool override_mode = mode_it == pending_.end() ? true : mode_it->second.override_active;
    const auto orig_it = originals_.find(identity);

    if (override_mode) {
        const std::int32_t kit = static_cast<std::int32_t>(values.paint_kit);
        const std::int32_t seed = static_cast<std::int32_t>(values.seed);
        if (!write_scalar(memory_, weapon + profile_.skins.fallback_paint_kit, kit)) return false;
        if (!write_scalar(memory_, weapon + profile_.skins.fallback_seed, seed)) return false;
        if (!write_scalar(memory_, weapon + profile_.skins.fallback_wear, values.wear)) return false;
        if (!write_scalar(memory_, weapon + profile_.skins.fallback_stattrak, values.stattrak)) return false;
        if (!write_scalar(memory_, item_view + profile_.skins.item_id_high, fallback_item_id_high)) return false;

        std::uint32_t account_id = ctx.local_account_id;
        if (account_id == 0) {
            read_scalar(memory_, weapon + profile_.skins.original_owner_xuid_low, account_id);
        }
        if (account_id != 0) {
            if (!write_scalar(memory_, item_view + profile_.skins.account_id, account_id)) return false;
        }
        if (values.stattrak >= 0) {
            if (!write_scalar(memory_, item_view + profile_.skins.entity_quality, stattrak_quality)) return false;
        } else if (orig_it != originals_.end()) {
            write_scalar(memory_, item_view + profile_.skins.entity_quality, orig_it->second.entity_quality);
        }
        if (mode_it != pending_.end()) {
            const std::string& custom_name = mode_it->second.extras.custom_name;
            if (!valid_custom_name(custom_name)) return false;
            if (!custom_name.empty()) {
                std::array<char, 33> name_buf{};
                std::memcpy(name_buf.data(), custom_name.data(), custom_name.size());
                if (!memory_.write(item_view + profile_.skins.custom_name, name_buf.data(), name_buf.size()))
                    return false;
            } else if (orig_it != originals_.end() && orig_it->second.has_custom_name) {
                memory_.write(item_view + profile_.skins.custom_name,
                              orig_it->second.original_name.data(), orig_it->second.original_name.size());
            }
        }
        return true;
    }

    // Restore mode: return weapon fields and econ metadata to captured baseline.
    const std::int32_t kit = orig_it != originals_.end() ? orig_it->second.raw_paint_kit : static_cast<std::int32_t>(values.paint_kit);
    const std::int32_t seed = orig_it != originals_.end() ? orig_it->second.raw_seed : static_cast<std::int32_t>(values.seed);
    const float wear = orig_it != originals_.end() ? orig_it->second.raw_wear : values.wear;
    const std::int32_t stattrak = orig_it != originals_.end() ? orig_it->second.raw_stattrak : values.stattrak;
    if (!write_scalar(memory_, weapon + profile_.skins.fallback_paint_kit, kit)) return false;
    if (!write_scalar(memory_, weapon + profile_.skins.fallback_seed, seed)) return false;
    if (!write_scalar(memory_, weapon + profile_.skins.fallback_wear, wear)) return false;
    if (!write_scalar(memory_, weapon + profile_.skins.fallback_stattrak, stattrak)) return false;
    if (orig_it != originals_.end()) {
        if (!write_scalar(memory_, item_view + profile_.skins.item_id_high, orig_it->second.item_id_high)) return false;
        if (!write_scalar(memory_, item_view + profile_.skins.account_id, orig_it->second.account_id)) return false;
        if (!write_scalar(memory_, item_view + profile_.skins.entity_quality, orig_it->second.entity_quality)) return false;
        if (orig_it->second.has_custom_name) {
            if (!memory_.write(item_view + profile_.skins.custom_name,
                               orig_it->second.original_name.data(), orig_it->second.original_name.size())) {
                return false;
            }
        }
    }
    return true;
}

bool MemoryCosmeticAdapter::refresh(std::uint64_t identity) {
    LocalContext ctx{};
    if (!resolve_context(ctx)) return false;
    std::uintptr_t weapon = 0;
    bool owned = false;
    if (!resolve_weapon(ctx, identity, weapon, owned) || !owned) return false;

    const auto mode_it = pending_.find(identity);
    const bool override_mode = mode_it == pending_.end() ? true : mode_it->second.override_active;
    const auto orig_it = originals_.find(identity);

    std::uint32_t vm_handle = 0;
    std::uintptr_t vm_entity = 0;
    if (read_scalar(memory_, weapon + profile_.skins.viewmodel_attachment, vm_handle)) {
        vm_entity = resolve_handle_with_serial(ctx.root, vm_handle, ctx.stride);
    }

    if (override_mode) {
        const std::uint64_t desired_mesh = mode_it != pending_.end() ? mode_it->second.extras.mesh_group_mask : 0;
        if (desired_mesh == 1 || desired_mesh == 2) {
            std::uint64_t current_mesh = 0;
            if (read_mesh_group(weapon, current_mesh)) {
                if (!write_mesh_group(weapon, desired_mesh)) return false;
            }
            if (vm_entity && read_mesh_group(vm_entity, current_mesh)) {
                if (!write_mesh_group(vm_entity, desired_mesh)) return false;
            }
        }
    } else if (orig_it != originals_.end()) {
        if (orig_it->second.has_weapon_mesh) {
            if (!write_mesh_group(weapon, orig_it->second.weapon_mesh_group)) return false;
        }
        if (vm_entity && orig_it->second.has_viewmodel_mesh) {
            if (!write_mesh_group(vm_entity, orig_it->second.viewmodel_mesh_group)) return false;
        }
    }

    std::int32_t reload_id = 0;
    if (read_scalar(memory_, weapon + profile_.skins.custom_econ_reload_id, reload_id)) {
        if (!write_scalar(memory_, weapon + profile_.skins.custom_econ_reload_id, reload_id + 1)) return false;
    }

    if (material_refresh_ && !material_refresh_(weapon)) return false;

    if (!override_mode) {
        originals_.erase(identity);
        pending_.erase(identity);
    }
    return true;
}

int32_t CosmeticController::apply(CosmeticAdapter& adapter, std::uint64_t identity,
                                  const PhantomCosmeticPreference& preference) {
    return apply(adapter, identity, preference, CosmeticExtras{});
}

int32_t CosmeticController::apply(CosmeticAdapter& adapter, std::uint64_t identity,
                                  const PhantomCosmeticPreference& preference,
                                  const CosmeticExtras& extras) {
    const CosmeticValues desired{preference.paint_kit, preference.seed, preference.wear, preference.stattrak};
    if (!identity || preference.struct_size != sizeof(preference) || !preference.weapon_definition ||
        preference.weapon_definition > 65535 || !valid_values(desired) ||
        !valid_custom_name(extras.custom_name) || !valid_mesh_group(extras.mesh_group_mask)) {
        return PHANTOM_INVALID_ARGUMENT;
    }
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
            *entry = {identity, current.weapon_definition, current.values, false, {}};
        }
        adapter.set_pending_extras(identity, extras);
        if (adapter.write(identity, desired) && adapter.refresh(identity)) {
            entry->had_override = true;
            entry->active_extras = extras;
            return PHANTOM_OK;
        }
        // Keep the original baseline even after failure so restore can be retried.
        // Re-read before rollback: the slot may now belong to a different entity.
        CosmeticItem after{};
        if (adapter.read(identity, after) && matching(after, identity, entry->weapon_definition)) {
            if (entry->had_override) adapter.set_pending_extras(identity, entry->active_extras);
            else adapter.clear_pending_extras(identity);
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
            adapter.clear_pending_extras(identity);
            *entry = {};
            return PHANTOM_STALE_DATA;
        }
        adapter.clear_pending_extras(identity);
        if (!adapter.write(identity, entry->baseline) || !adapter.refresh(identity)) return PHANTOM_INTERNAL_ERROR;
        *entry = {};
        return PHANTOM_OK;
    } catch (...) { return PHANTOM_INTERNAL_ERROR; }
}

int32_t CosmeticController::apply_loadout(CosmeticAdapter& adapter,
                                          const std::vector<CosmeticPreferenceEntry>& loadout,
                                          CosmeticRunReport& report) {
    report = {};
    std::vector<CosmeticItem> weapons;
    if (!adapter.enumerate_local_weapons(weapons)) return PHANTOM_STALE_DATA;
    report.weapons_found = static_cast<std::uint32_t>(weapons.size());

    // Restore or prune previously overridden weapons whose definitions were removed or dropped.
    std::vector<std::pair<std::uint64_t, std::uint32_t>> tracked;
    for (const Entry& entry : entries_) {
        if (entry.identity) tracked.emplace_back(entry.identity, entry.weapon_definition);
    }
    for (const auto& [identity, def] : tracked) {
        const bool present_locally = std::any_of(weapons.begin(), weapons.end(),
                                                 [identity](const CosmeticItem& w) { return w.identity == identity; });
        const bool still_configured = std::any_of(loadout.begin(), loadout.end(),
                                                  [def](const CosmeticPreferenceEntry& p) {
                                                      return p.preference.weapon_definition == def;
                                                  });
        if (!still_configured) {
            const int32_t status = restore(adapter, identity);
            if (status == PHANTOM_OK) ++report.weapons_restored;
            else if (status == PHANTOM_INTERNAL_ERROR) ++report.weapons_failed;
        } else if (!present_locally) {
            CosmeticItem probe{};
            if (!adapter.read(identity, probe) || !matching(probe, identity, def)) {
                auto slot = std::find_if(entries_.begin(), entries_.end(),
                                         [identity](const Entry& e) { return e.identity == identity; });
                if (slot != entries_.end()) {
                    adapter.clear_pending_extras(identity);
                    *slot = {};
                }
            }
        }
    }

    for (const CosmeticItem& weapon : weapons) {
        const auto pref_it = std::find_if(loadout.begin(), loadout.end(),
                                          [&weapon](const CosmeticPreferenceEntry& p) {
                                              return p.preference.weapon_definition == weapon.weapon_definition;
                                          });
        if (pref_it == loadout.end()) continue;
        const CosmeticValues desired{pref_it->preference.paint_kit, pref_it->preference.seed,
                                     pref_it->preference.wear, pref_it->preference.stattrak};
        const auto existing = std::find_if(entries_.begin(), entries_.end(),
                                           [&weapon](const Entry& e) { return e.identity == weapon.identity; });
        if (existing != entries_.end() && existing->had_override &&
            values_equal(weapon.values, desired) && extras_equal(existing->active_extras, pref_it->extras)) {
            continue;
        }
        const int32_t status = apply(adapter, weapon.identity, pref_it->preference, pref_it->extras);
        if (status == PHANTOM_OK) ++report.weapons_applied;
        else ++report.weapons_failed;
    }
    return report.weapons_failed == 0 ? PHANTOM_OK : PHANTOM_INTERNAL_ERROR;
}

int32_t CosmeticController::restore_all(CosmeticAdapter& adapter, CosmeticRunReport& report) {
    report = {};
    std::vector<std::uint64_t> active;
    for (const Entry& entry : entries_) {
        if (entry.identity) active.push_back(entry.identity);
    }
    report.weapons_found = static_cast<std::uint32_t>(active.size());
    for (std::uint64_t identity : active) {
        const int32_t status = restore(adapter, identity);
        if (status == PHANTOM_OK) ++report.weapons_restored;
        else if (status == PHANTOM_INTERNAL_ERROR) ++report.weapons_failed;
    }
    return report.weapons_failed == 0 ? PHANTOM_OK : PHANTOM_INTERNAL_ERROR;
}

std::size_t CosmeticController::active_count() const {
    return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(),
                                                  [](const Entry& e) { return e.identity != 0; }));
}
} // namespace phantom
