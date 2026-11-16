"""Menu visibility polling, separate from the game worker and its input controls."""
from __future__ import annotations

import sys

# A generic modifier aliases either side; two different sides are distinct.
MODIFIERS = {0x10: (0xA0, 0xA1), 0x11: (0xA2, 0xA3), 0x12: (0xA4, 0xA5)}


def keys_conflict(a, b):
    return a == b or b in MODIFIERS.get(a, ()) or a in MODIFIERS.get(b, ())


def capture_vk(qt_key, native_vk=0, scan_code=0):
    """Preserve modifier sides even when Windows reports generic VK_SHIFT."""
    if native_vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
        return native_vk
    if qt_key == 0x01000020 and scan_code & 0xFF in (0x2A, 0x36):
        return 0xA1 if scan_code & 0xFF == 0x36 else 0xA0
    if qt_key in (0x01000021, 0x01000023) and scan_code:
        right = bool(scan_code & 0x100)
        return (0xA3 if right else 0xA2) if qt_key == 0x01000021 else (0xA5 if right else 0xA4)
    if 1 <= native_vk <= 254:
        return native_vk
    special = {0x01000020: 0x10, 0x01000021: 0x11, 0x01000023: 0x12,
               0x20: 0x20, 0x01000011: 0x23, 0x01000010: 0x24,
               0x01000006: 0x2D, 0x01000007: 0x2E}
    if qt_key in special:
        return special[qt_key]
    if 0x30 <= qt_key <= 0x5A:
        return qt_key
    if 0x01000030 <= qt_key <= 0x0100003B:
        return 0x70 + qt_key - 0x01000030
    return 0


def windows_key_reader():
    if sys.platform != 'win32':
        return lambda vk: False
    import ctypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    read = user.GetAsyncKeyState
    read.argtypes, read.restype = [ctypes.c_int], ctypes.c_short
    return lambda vk: bool(read(vk) & 0x8000)


class MenuHotkey:
    def __init__(self, read_key=None):
        self.read_key = read_key if read_key is not None else windows_key_reader()
        self.key = None
        self.down = False

    def prime(self, key):
        self.key, self.down = key, self.read_key(key)

    def poll(self, key, blocked=False):
        if key != self.key:
            self.prime(key)
            return False
        down = self.read_key(key)
        pressed = down and not self.down
        self.down = down  # Track releases even during capture/modal dialogs.
        return pressed and not blocked
