#include "phantom/runtime.h"
#include "phantom/core.h"
#include "phantom/cosmetics.h"
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {
constexpr std::size_t max_skin_file_bytes = 65536;
std::atomic<bool> g_skin_loadout_enabled{true};

void clear_timing(PhantomBombTiming* out) {
    if (!out) return;
    *out = {};
    out->struct_size = sizeof(*out);
    out->phase = PHANTOM_BOMB_UNAVAILABLE;
}

void clear_skin_report(PhantomSkinApplyReport* out) {
    if (!out) return;
    *out = {};
    out->struct_size = sizeof(*out);
}

bool valid_watcher_options(const PhantomSkinWatcherOptions* options) {
    if (!options || options->struct_size != sizeof(*options)) return false;
    if (options->poll_interval_ms < 50 || options->poll_interval_ms > 5000) return false;
    if (options->restore_on_stop > 1) return false;
    const void* nul = std::memchr(options->loadout_json_path, '\0', sizeof(options->loadout_json_path));
    return nul != nullptr;
}
} // namespace

namespace phantom {
void set_skin_loadout_enabled(bool enabled) {
    g_skin_loadout_enabled.store(enabled);
}
} // namespace phantom

int32_t PHANTOM_CALL phantom_runtime_load_skin_file(const char* path) {
    if (!path || path[0] == '\0') return PHANTOM_INVALID_ARGUMENT;
    try {
        std::ifstream stream(std::filesystem::u8path(path), std::ios::binary | std::ios::ate);
        if (!stream.is_open()) return PHANTOM_NOT_FOUND;
        const std::streamoff length = stream.tellg();
        if (length <= 0 || static_cast<std::size_t>(length) > max_skin_file_bytes)
            return PHANTOM_INVALID_ARGUMENT;
        stream.seekg(0, std::ios::beg);
        std::string content(static_cast<std::size_t>(length), '\0');
        if (!stream.read(content.data(), length)) return PHANTOM_INTERNAL_ERROR;

        bool enabled = false;
        std::vector<phantom::CosmeticPreferenceEntry> entries;
        if (!phantom::parse_skin_loadout_json(content, enabled, entries))
            return PHANTOM_INVALID_ARGUMENT;
        const int32_t replaced = phantom::replace_cosmetic_preferences(entries);
        if (replaced != PHANTOM_OK) return replaced;
        g_skin_loadout_enabled.store(enabled);
        return PHANTOM_OK;
    } catch (...) {
        return PHANTOM_INTERNAL_ERROR;
    }
}

#if defined(_WIN32)
#ifndef UNICODE
#define UNICODE
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace {
constexpr wchar_t overlay_class[] = L"PhantomBombTimerOverlay";

class ProcessMemory final : public phantom::IMemory {
public:
    bool read(std::uintptr_t address, void* output, std::size_t size) const override {
        if (!address || !output) return false;
        SIZE_T bytes_read = 0;
        if (!ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<LPCVOID>(address), output, size, &bytes_read))
            return false;
        return bytes_read == size;
    }
};

class ReadWriteProcessMemory final : public phantom::IProcessMemory {
public:
    bool read(std::uintptr_t address, void* output, std::size_t size) const override {
        if (!address || !output) return false;
        SIZE_T bytes_read = 0;
        if (!ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<LPCVOID>(address), output, size, &bytes_read))
            return false;
        return bytes_read == size;
    }
    bool write(std::uintptr_t address, const void* input, std::size_t size) override {
        if (!address || !input) return false;
        SIZE_T bytes_written = 0;
        if (!WriteProcessMemory(GetCurrentProcess(), reinterpret_cast<LPVOID>(address), input, size, &bytes_written))
            return false;
        return bytes_written == size;
    }
};

std::uintptr_t client_base() {
    HMODULE module = GetModuleHandleW(L"client.dll");
    return module ? reinterpret_cast<std::uintptr_t>(module) : 0;
}

std::wstring utf8_to_wide(const char* value) {
    if (!value || !value[0]) return {};
    const int needed = MultiByteToWideChar(CP_UTF8, 0, value, -1, nullptr, 0);
    if (needed <= 1) return {};
    std::wstring result(static_cast<std::size_t>(needed), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value, -1, result.data(), needed);
    result.pop_back();
    return result;
}

std::uint32_t color_from_runtime(const PhantomBombOverlayOptions* options) {
    return options ? options->color_rgb : 0x00ffffffu;
}

std::wstring timing_text(const PhantomBombTiming& timing) {
    auto remaining = [](double seconds) {
        wchar_t buffer[32]{};
        std::swprintf(buffer, sizeof(buffer) / sizeof(buffer[0]), L"%.1fs", std::max(0.0, seconds));
        return std::wstring(buffer);
    };
    const wchar_t site = timing.site == 1 ? L'A' : timing.site == 2 ? L'B' : L'?';
    switch (timing.phase) {
        case PHANTOM_BOMB_TICKING:
            return std::wstring(L"site ") + site + L" bomb: " + remaining(timing.explosion_remaining);
        case PHANTOM_BOMB_DEFUSING: {
            std::wstring text = std::wstring(L"site ") + site + L" | bomb " + remaining(timing.explosion_remaining) +
                                L" | defuse " + remaining(timing.defuse_remaining);
            if (timing.defuse_estimate == PHANTOM_DEFUSE_EXPECTED_BEFORE) text += L" | defuse first";
            else if (timing.defuse_estimate == PHANTOM_DEFUSE_EXPECTED_AFTER) text += L" | bomb first";
            return text;
        }
        case PHANTOM_BOMB_DEFUSED:
            return std::wstring(L"site ") + site + L" bomb defused";
        case PHANTOM_BOMB_EXPIRED:
            return std::wstring(L"site ") + site + L" detonation time elapsed";
        default:
            return L"";
    }
}

struct OverlayState {
    std::mutex mutex;
    HANDLE thread = nullptr;
    DWORD thread_id = 0;
    HWND window = nullptr;
    PhantomBombOverlayOptions options{sizeof(PhantomBombOverlayOptions), 24, 24, 420, 56, 24, 0x00ffffffu};
    bool stop_requested = false;
};
OverlayState g_state;

struct SkinRuntimeState {
    std::mutex engine_mutex;
    ReadWriteProcessMemory memory;
    std::uintptr_t bound_base = 0;
    std::unique_ptr<phantom::MemoryCosmeticAdapter> adapter;
    phantom::CosmeticController controller;

    std::mutex watcher_mutex;
    HANDLE thread = nullptr;
    HANDLE stop_event = nullptr;
    PhantomSkinWatcherOptions options{};
};
SkinRuntimeState g_skin_state;

phantom::MemoryCosmeticAdapter* ensure_skin_adapter_locked(std::uintptr_t base) {
    if (!base) {
        g_skin_state.adapter.reset();
        g_skin_state.bound_base = 0;
        return nullptr;
    }
    if (!g_skin_state.adapter || g_skin_state.bound_base != base) {
        g_skin_state.adapter = std::make_unique<phantom::MemoryCosmeticAdapter>(
            g_skin_state.memory, base, phantom::Profile::reference_26598758());
        g_skin_state.controller = phantom::CosmeticController{};
        g_skin_state.bound_base = base;
    }
    return g_skin_state.adapter.get();
}

int32_t apply_skins_win(PhantomSkinApplyReport* out) {
    clear_skin_report(out);
    const std::uintptr_t base = client_base();
    if (!base) return PHANTOM_NOT_INTEGRATED;
    try {
        std::lock_guard<std::mutex> lock(g_skin_state.engine_mutex);
        auto* adapter = ensure_skin_adapter_locked(base);
        if (!adapter) return PHANTOM_NOT_INTEGRATED;
        phantom::CosmeticRunReport run{};
        int32_t status = PHANTOM_OK;
        if (!g_skin_loadout_enabled.load()) {
            status = g_skin_state.controller.restore_all(*adapter, run);
        } else {
            std::vector<phantom::CosmeticPreferenceEntry> loadout;
            phantom::snapshot_cosmetic_preferences(loadout);
            status = g_skin_state.controller.apply_loadout(*adapter, loadout, run);
        }
        out->weapons_found = run.weapons_found;
        out->weapons_applied = run.weapons_applied;
        out->weapons_restored = run.weapons_restored;
        out->weapons_failed = run.weapons_failed;
        return status;
    } catch (...) {
        clear_skin_report(out);
        return PHANTOM_INTERNAL_ERROR;
    }
}

int32_t restore_skins_win(PhantomSkinApplyReport* out) {
    clear_skin_report(out);
    const std::uintptr_t base = client_base();
    if (!base) return PHANTOM_NOT_INTEGRATED;
    try {
        std::lock_guard<std::mutex> lock(g_skin_state.engine_mutex);
        auto* adapter = ensure_skin_adapter_locked(base);
        if (!adapter) return PHANTOM_NOT_INTEGRATED;
        phantom::CosmeticRunReport run{};
        const int32_t status = g_skin_state.controller.restore_all(*adapter, run);
        out->weapons_found = run.weapons_found;
        out->weapons_applied = run.weapons_applied;
        out->weapons_restored = run.weapons_restored;
        out->weapons_failed = run.weapons_failed;
        return status;
    } catch (...) {
        clear_skin_report(out);
        return PHANTOM_INTERNAL_ERROR;
    }
}

DWORD WINAPI skin_watcher_thread(LPVOID parameter) {
    std::unique_ptr<PhantomSkinWatcherOptions> supplied(static_cast<PhantomSkinWatcherOptions*>(parameter));
    const PhantomSkinWatcherOptions options = supplied ? *supplied : PhantomSkinWatcherOptions{};
    const std::string path_utf8(options.loadout_json_path);
    const std::wstring path_wide = utf8_to_wide(path_utf8.c_str());
    FILETIME last_write{};
    DWORD last_size_low = 0;
    bool has_file_stamp = false;

    for (;;) {
        if (!path_wide.empty()) {
            WIN32_FILE_ATTRIBUTE_DATA attrs{};
            if (GetFileAttributesExW(path_wide.c_str(), GetFileExInfoStandard, &attrs)) {
                const bool changed = !has_file_stamp ||
                                     attrs.ftLastWriteTime.dwLowDateTime != last_write.dwLowDateTime ||
                                     attrs.ftLastWriteTime.dwHighDateTime != last_write.dwHighDateTime ||
                                     attrs.nFileSizeLow != last_size_low;
                if (changed) {
                    if (phantom_runtime_load_skin_file(path_utf8.c_str()) == PHANTOM_OK) {
                        last_write = attrs.ftLastWriteTime;
                        last_size_low = attrs.nFileSizeLow;
                        has_file_stamp = true;
                    }
                }
            }
        }
        PhantomSkinApplyReport report{};
        report.struct_size = sizeof(report);
        apply_skins_win(&report);

        HANDLE stop_event = nullptr;
        {
            std::lock_guard<std::mutex> lock(g_skin_state.watcher_mutex);
            stop_event = g_skin_state.stop_event;
        }
        if (!stop_event || WaitForSingleObject(stop_event, options.poll_interval_ms) == WAIT_OBJECT_0) {
            break;
        }
    }

    if (options.restore_on_stop) {
        PhantomSkinApplyReport report{};
        report.struct_size = sizeof(report);
        restore_skins_win(&report);
    }
    return 0;
}

int32_t capture_bomb_win(PhantomBombTiming* out) {
    if (!out) return PHANTOM_INVALID_ARGUMENT;
    clear_timing(out);
    const std::uintptr_t base = client_base();
    if (!base) return PHANTOM_NOT_INTEGRATED;
    try {
        ProcessMemory memory;
        phantom::Decoder decoder(memory, base, phantom::Profile::reference_26598758());
        const phantom::BombSnapshot source = decoder.capture_bomb();
        if (!source.valid || !source.planted) return PHANTOM_OK;
        PhantomBombSnapshot snapshot{};
        snapshot.struct_size = sizeof(snapshot);
        snapshot.valid = 1;
        snapshot.planted = source.planted ? 1u : 0u;
        snapshot.defused = source.defused ? 1u : 0u;
        snapshot.defusing = source.defusing ? 1u : 0u;
        snapshot.site = source.site;
        snapshot.game_time = source.game_time;
        snapshot.detonation_time = source.detonation_time;
        snapshot.defuse_end_time = source.defuse_end_time;
        snapshot.observation_age = 0.0;
        return phantom_evaluate_bomb(&snapshot, out);
    } catch (...) {
        clear_timing(out);
        // A build mismatch or unreadable frame must not leave a stale countdown visible.
        return PHANTOM_STALE_DATA;
    }
}

LRESULT CALLBACK overlay_window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_TIMER) {
        InvalidateRect(window, nullptr, FALSE);
        return 0;
    }
    if (message == WM_PAINT) {
        PAINTSTRUCT paint{};
        HDC dc = BeginPaint(window, &paint);
        PhantomBombOverlayOptions options;
        {
            std::lock_guard<std::mutex> lock(g_state.mutex);
            options = g_state.options;
        }
        HBRUSH black = CreateSolidBrush(RGB(0, 0, 0));
        RECT client{0, 0, static_cast<LONG>(options.width), static_cast<LONG>(options.height)};
        FillRect(dc, &client, black);
        DeleteObject(black);
        PhantomBombTiming timing{};
        timing.struct_size = sizeof(timing);
        capture_bomb_win(&timing);
        const std::wstring text = timing_text(timing);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, static_cast<COLORREF>(color_from_runtime(&options)));
        HFONT font = CreateFontW(-static_cast<int>(options.font_height), 0, 0, 0, FW_SEMIBOLD,
                                 FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                                 CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Poppins");
        HGDIOBJ old_font = font ? SelectObject(dc, font) : nullptr;
        if (!text.empty())
            TextOutW(dc, 8, 8, text.c_str(), static_cast<int>(text.size()));
        if (old_font) SelectObject(dc, old_font);
        if (font) DeleteObject(font);
        EndPaint(window, &paint);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

DWORD WINAPI overlay_thread(LPVOID parameter) {
    std::unique_ptr<PhantomBombOverlayOptions> supplied(static_cast<PhantomBombOverlayOptions*>(parameter));
    PhantomBombOverlayOptions options = supplied ? *supplied : g_state.options;
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        g_state.options = options;
        g_state.stop_requested = false;
    }
    WNDCLASSEXW window_class{};
    window_class.cbSize = sizeof(window_class);
    window_class.lpfnWndProc = overlay_window_proc;
    window_class.hInstance = GetModuleHandleW(nullptr);
    window_class.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
    window_class.lpszClassName = overlay_class;
    RegisterClassExW(&window_class); // An existing class from a prior overlay run is reusable.
    HWND window = CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
                                  overlay_class, L"Phantom bomb timer", WS_POPUP,
                                  options.x, options.y, static_cast<int>(options.width), static_cast<int>(options.height),
                                  nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    if (!window) {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        g_state.window = nullptr;
        return 1;
    }
    SetLayeredWindowAttributes(window, RGB(0, 0, 0), 0, LWA_COLORKEY);
    SetWindowPos(window, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
    ShowWindow(window, SW_SHOWNA);
    SetTimer(window, 1, 50, nullptr);
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        g_state.window = window;
        g_state.thread_id = GetCurrentThreadId();
    }
    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    KillTimer(window, 1);
    DestroyWindow(window);
    UnregisterClassW(overlay_class, GetModuleHandleW(nullptr));
    std::lock_guard<std::mutex> lock(g_state.mutex);
    g_state.window = nullptr;
    g_state.thread_id = 0;
    return 0;
}
} // namespace

uint32_t PHANTOM_CALL phantom_runtime_is_available(void) {
    return client_base() ? 1u : 0u;
}
int32_t PHANTOM_CALL phantom_runtime_capture_bomb(PhantomBombTiming* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    if (!client_base()) {
        clear_timing(out);
        return PHANTOM_NOT_INTEGRATED;
    }
    return capture_bomb_win(out);
}
int32_t PHANTOM_CALL phantom_runtime_start_bomb_overlay(const PhantomBombOverlayOptions* options) {
    if (!options || options->struct_size != sizeof(*options)) return PHANTOM_INVALID_ARGUMENT;
    if (options->width < 120 || options->width > 1200 || options->height < 24 || options->height > 240 ||
        options->font_height < 8 || options->font_height > 96 || (options->color_rgb & 0xff000000u) != 0)
        return PHANTOM_INVALID_ARGUMENT;
    if (!client_base()) return PHANTOM_NOT_INTEGRATED;
    std::lock_guard<std::mutex> lock(g_state.mutex);
    if (g_state.thread) return PHANTOM_OK;
    g_state.stop_requested = false;
    auto* copy = new PhantomBombOverlayOptions(*options);
    HANDLE thread = CreateThread(nullptr, 0, overlay_thread, copy, CREATE_SUSPENDED, &g_state.thread_id);
    if (!thread) {
        delete copy;
        return PHANTOM_INTERNAL_ERROR;
    }
    g_state.thread = thread;
    ResumeThread(thread);
    return PHANTOM_OK;
}
int32_t PHANTOM_CALL phantom_runtime_stop_bomb_overlay(void) {
    HANDLE thread = nullptr;
    DWORD thread_id = 0;
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        if (!g_state.thread) return PHANTOM_OK;
        g_state.stop_requested = true;
        thread = g_state.thread;
        thread_id = g_state.thread_id;
    }
    if (thread_id) PostThreadMessageW(thread_id, WM_QUIT, 0, 0);
    const DWORD waited = WaitForSingleObject(thread, 1000);
    CloseHandle(thread);
    std::lock_guard<std::mutex> lock(g_state.mutex);
    g_state.thread = nullptr;
    g_state.thread_id = 0;
    return waited == WAIT_OBJECT_0 ? PHANTOM_OK : PHANTOM_INTERNAL_ERROR;
}

int32_t PHANTOM_CALL phantom_runtime_apply_skins(PhantomSkinApplyReport* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    return apply_skins_win(out);
}
int32_t PHANTOM_CALL phantom_runtime_restore_skins(PhantomSkinApplyReport* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    return restore_skins_win(out);
}
int32_t PHANTOM_CALL phantom_runtime_start_skin_watcher(const PhantomSkinWatcherOptions* options) {
    if (!valid_watcher_options(options)) return PHANTOM_INVALID_ARGUMENT;
    if (!client_base()) return PHANTOM_NOT_INTEGRATED;
    std::lock_guard<std::mutex> lock(g_skin_state.watcher_mutex);
    if (g_skin_state.thread) return PHANTOM_OK;
    HANDLE stop_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!stop_event) return PHANTOM_INTERNAL_ERROR;
    g_skin_state.options = *options;
    g_skin_state.stop_event = stop_event;
    auto* copy = new PhantomSkinWatcherOptions(*options);
    HANDLE thread = CreateThread(nullptr, 0, skin_watcher_thread, copy, 0, nullptr);
    if (!thread) {
        delete copy;
        CloseHandle(stop_event);
        g_skin_state.stop_event = nullptr;
        return PHANTOM_INTERNAL_ERROR;
    }
    g_skin_state.thread = thread;
    return PHANTOM_OK;
}
int32_t PHANTOM_CALL phantom_runtime_stop_skin_watcher(void) {
    HANDLE thread = nullptr;
    HANDLE stop_event = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_skin_state.watcher_mutex);
        if (!g_skin_state.thread) return PHANTOM_OK;
        thread = g_skin_state.thread;
        stop_event = g_skin_state.stop_event;
    }
    if (stop_event) SetEvent(stop_event);
    const DWORD waited = WaitForSingleObject(thread, 2000);
    CloseHandle(thread);
    if (stop_event) CloseHandle(stop_event);
    std::lock_guard<std::mutex> lock(g_skin_state.watcher_mutex);
    g_skin_state.thread = nullptr;
    g_skin_state.stop_event = nullptr;
    return waited == WAIT_OBJECT_0 ? PHANTOM_OK : PHANTOM_INTERNAL_ERROR;
}

#else
uint32_t PHANTOM_CALL phantom_runtime_is_available(void) { return 0; }
int32_t PHANTOM_CALL phantom_runtime_capture_bomb(PhantomBombTiming* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    clear_timing(out);
    return PHANTOM_NOT_INTEGRATED;
}
int32_t PHANTOM_CALL phantom_runtime_start_bomb_overlay(const PhantomBombOverlayOptions* options) {
    if (!options || options->struct_size != sizeof(*options)) return PHANTOM_INVALID_ARGUMENT;
    return PHANTOM_NOT_INTEGRATED;
}
int32_t PHANTOM_CALL phantom_runtime_stop_bomb_overlay(void) { return PHANTOM_OK; }

int32_t PHANTOM_CALL phantom_runtime_apply_skins(PhantomSkinApplyReport* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    clear_skin_report(out);
    return PHANTOM_NOT_INTEGRATED;
}
int32_t PHANTOM_CALL phantom_runtime_restore_skins(PhantomSkinApplyReport* out) {
    if (!out || out->struct_size != sizeof(*out)) return PHANTOM_INVALID_ARGUMENT;
    clear_skin_report(out);
    return PHANTOM_NOT_INTEGRATED;
}
int32_t PHANTOM_CALL phantom_runtime_start_skin_watcher(const PhantomSkinWatcherOptions* options) {
    if (!valid_watcher_options(options)) return PHANTOM_INVALID_ARGUMENT;
    return PHANTOM_NOT_INTEGRATED;
}
int32_t PHANTOM_CALL phantom_runtime_stop_skin_watcher(void) { return PHANTOM_OK; }
#endif
