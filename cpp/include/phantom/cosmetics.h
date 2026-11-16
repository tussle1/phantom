#pragma once

#include "phantom/api.h"
#include <array>
#include <cstdint>

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
struct CosmeticItem {
    std::uint64_t identity = 0;
    std::uint32_t weapon_definition = 0;
    bool owned_local = false;
    CosmeticValues values{};
};
class CosmeticAdapter {
public:
    virtual ~CosmeticAdapter() = default;
    virtual bool read(std::uint64_t identity, CosmeticItem& item) = 0;
    // A failing write may have partially changed the item.
    virtual bool write(std::uint64_t identity, const CosmeticValues& values) = 0;
    // Rebuild local weapon and viewmodel materials; never network inventory.
    virtual bool refresh(std::uint64_t identity) = 0;
};

// A host owns this controller and calls it only on the game thread. There is no
// live CS2 adapter in Phantom yet; this class does not discover game memory.
class CosmeticController {
public:
    int32_t apply(CosmeticAdapter& adapter, std::uint64_t identity,
                  const PhantomCosmeticPreference& preference);
    int32_t restore(CosmeticAdapter& adapter, std::uint64_t identity);
private:
    struct Entry {
        std::uint64_t identity = 0;
        std::uint32_t weapon_definition = 0;
        CosmeticValues baseline{};
    };
    std::array<Entry, 32> entries_{};
};

} // namespace phantom
