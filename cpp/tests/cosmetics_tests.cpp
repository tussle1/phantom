#include "phantom/cosmetics.h"
#include <cmath>
#include <cstdio>
#include <limits>

namespace {
int failures = 0;
void check(bool result, const char* message) {
    if (!result) { std::fprintf(stderr, "FAIL: %s\n", message); ++failures; }
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
PhantomCosmeticPreference pref() {
    return {sizeof(PhantomCosmeticPreference), 7, 123, 20, 0.1f, 44};
}
void tests() {
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
}
int main() {
    tests();
    if (failures) return 1;
    std::puts("cosmetic controller tests passed");
    return 0;
}
