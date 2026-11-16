#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include "phantom/runtime.h"

using PhantomAbiFn = uint32_t(__cdecl *)();
using PhantomStatusFn = int32_t(__cdecl *)(void*);
using PhantomAvailabilityFn = uint32_t(__cdecl *)();
struct PhantomStatusLayout {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t game_adapter_ready;
    uint32_t live_bomb_timer_ready;
    uint32_t cosmetic_changes_ready;
    char reason[160];
};

std::wstring utf8_to_wide(const char* value) {
    int chars = MultiByteToWideChar(CP_UTF8, 0, value, -1, nullptr, 0);
    if (chars <= 1) return {};
    std::wstring result(static_cast<size_t>(chars), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value, -1, result.data(), chars);
    result.pop_back();
    return result;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: phantom_dll_smoke <path-to-phantom-internal-foundation.dll>\n");
        return 2;
    }
    HMODULE module = LoadLibraryW(utf8_to_wide(argv[1]).c_str());
    if (!module) {
        std::fprintf(stderr, "LoadLibrary failed: %lu\n", GetLastError());
        return 3;
    }
    auto abi = reinterpret_cast<PhantomAbiFn>(GetProcAddress(module, "phantom_abi_version"));
    auto status = reinterpret_cast<PhantomStatusFn>(GetProcAddress(module, "phantom_get_integration_status"));
    auto runtime_available = reinterpret_cast<PhantomAvailabilityFn>(GetProcAddress(module, "phantom_runtime_is_available"));
    auto apply_skins = reinterpret_cast<int32_t(__cdecl *)(PhantomSkinApplyReport*)>(
        GetProcAddress(module, "phantom_runtime_apply_skins"));
    auto restore_skins = reinterpret_cast<int32_t(__cdecl *)(PhantomSkinApplyReport*)>(
        GetProcAddress(module, "phantom_runtime_restore_skins"));
    auto load_skin_file = GetProcAddress(module, "phantom_runtime_load_skin_file");
    auto start_skin_watcher = GetProcAddress(module, "phantom_runtime_start_skin_watcher");
    auto stop_skin_watcher = GetProcAddress(module, "phantom_runtime_stop_skin_watcher");
    int result = 0;
    if (!abi || !status || !runtime_available || !apply_skins || !restore_skins ||
        !load_skin_file || !start_skin_watcher || !stop_skin_watcher ||
        abi() != 1 || runtime_available() != 0) {
        std::fprintf(stderr, "expected ABI/runtime symbols missing, invalid, or unexpectedly available without the game\n");
        result = 4;
    } else {
        PhantomStatusLayout s{};
        s.struct_size = sizeof(s);
        PhantomSkinApplyReport report{};
        report.struct_size = sizeof(report);
        if (status(&s) != 0 || s.abi_version != 1 || s.game_adapter_ready != 0 ||
            apply_skins(&report) != PHANTOM_NOT_INTEGRATED ||
            restore_skins(&report) != PHANTOM_NOT_INTEGRATED) {
            std::fprintf(stderr, "DLL status/skin contract failed\n");
            result = 5;
        }
    }
    FreeLibrary(module);
    if (result == 0) std::puts("Windows DLL load/unload smoke passed");
    return result;
}
