"""Small Win32 startup console matching Phantom's native visual identity."""
from __future__ import annotations

import ctypes
import os
import sys

_ACCENT = '\x1b[38;2;113;119;210m'
_BODY = '\x1b[38;2;195;200;215m'
_DIM = '\x1b[38;2;90;95;110m'
_RESET = '\x1b[0m'
_initialized = False


def _kernel32():
    return ctypes.WinDLL('kernel32', use_last_error=True)


def initialize() -> bool:
    """Create a console for the windowed build, then apply the reference sizing."""
    global _initialized
    if _initialized or sys.platform != 'win32':
        return _initialized
    kernel = _kernel32()
    kernel.GetConsoleWindow.restype = ctypes.c_void_p
    kernel.GetStdHandle.argtypes = (ctypes.c_ulong,)
    kernel.GetStdHandle.restype = ctypes.c_void_p
    # PyInstaller's --windowed executable has no console. Development launches may.
    if not kernel.GetConsoleWindow() and not kernel.AllocConsole():
        return False
    for name, mode in (('CONOUT$', 'w'), ('CONIN$', 'r')):
        try:
            stream = open(name, mode, encoding='utf-8', buffering=1)
            if name == 'CONOUT$':
                sys.stdout = stream
                sys.stderr = stream
            else:
                sys.stdin = stream
        except OSError:
            pass
    output = kernel.GetStdHandle(-11)
    current = ctypes.c_ulong()
    if kernel.GetConsoleMode(output, ctypes.byref(current)):
        kernel.SetConsoleMode(output, current.value | 0x0004)
    kernel.SetConsoleTitleW('phantom')
    hwnd = kernel.GetConsoleWindow()
    if hwnd:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetWindowLongW.argtypes = (ctypes.c_void_p, ctypes.c_int)
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)
        user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint)
        style = user32.GetWindowLongW(hwnd, -16)
        user32.SetWindowLongW(hwnd, -16, style & ~0x00010000 & ~0x00040000)
        user32.SetWindowPos(hwnd, 0, 0, 0, 775, 440, 0x0004 | 0x0010)
    os.system('color 07')
    _initialized = True
    print()
    emit('console initialized.')
    return True


def emit(message: str) -> None:
    if not _initialized:
        return
    print(f'  {_ACCENT}phantom{_DIM} - {_BODY}{message}{_RESET}', flush=True)
