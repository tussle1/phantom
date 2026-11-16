"""Capture real Windows CMD startup text and colours, redrawn into an MP4.

Requires Windows, Pillow 11.2.1, imageio-ffmpeg 0.6.0 and GUI dependencies.
Frames come from the started program's Windows console screen buffer. The
window chrome is drawn, not a screen capture. No game worker is started.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


class Coord(ctypes.Structure):
    _fields_ = [('X', wintypes.SHORT), ('Y', wintypes.SHORT)]


class SmallRect(ctypes.Structure):
    _fields_ = [('Left', wintypes.SHORT), ('Top', wintypes.SHORT),
                ('Right', wintypes.SHORT), ('Bottom', wintypes.SHORT)]


class ConsoleInfo(ctypes.Structure):
    _fields_ = [('dwSize', Coord), ('dwCursorPosition', Coord),
                ('wAttributes', wintypes.WORD), ('srWindow', SmallRect),
                ('dwMaximumWindowSize', Coord)]


class CharUnion(ctypes.Union):
    _fields_ = [('UnicodeChar', wintypes.WCHAR), ('AsciiChar', ctypes.c_char)]


class CharInfo(ctypes.Structure):
    _anonymous_ = ('Char',)
    _fields_ = [('Char', CharUnion), ('Attributes', wintypes.WORD)]


class ConsoleCapture:
    def __init__(self, pid):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.FreeConsole.argtypes = (); k.FreeConsole.restype = wintypes.BOOL
        k.AttachConsole.argtypes = (wintypes.DWORD,); k.AttachConsole.restype = wintypes.BOOL
        k.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        k.CreateFileW.restype = wintypes.HANDLE
        k.GetConsoleScreenBufferInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(ConsoleInfo))
        k.GetConsoleScreenBufferInfo.restype = wintypes.BOOL
        k.ReadConsoleOutputW.argtypes = (wintypes.HANDLE, ctypes.POINTER(CharInfo), Coord, Coord,
                                         ctypes.POINTER(SmallRect))
        k.ReadConsoleOutputW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = (wintypes.HANDLE,); k.CloseHandle.restype = wintypes.BOOL
        # This process's standard streams are the runner's pipes; the captured
        # child owns a distinct console because CREATE_NEW_CONSOLE was used.
        k.FreeConsole()
        if not k.AttachConsole(pid):
            raise ctypes.WinError(ctypes.get_last_error())
        self.kernel = k
        self.handle = k.CreateFileW('CONOUT$', 0x80000000, 3, None, 3, 0, None)
        if self.handle == wintypes.HANDLE(-1).value:
            k.FreeConsole()
            raise ctypes.WinError(ctypes.get_last_error())

    def read(self):
        info = ConsoleInfo()
        if not self.kernel.GetConsoleScreenBufferInfo(self.handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        width = min(110, info.srWindow.Right-info.srWindow.Left+1)
        height = min(24, info.srWindow.Bottom-info.srWindow.Top+1)
        if width <= 0 or height <= 0:
            raise RuntimeError('Invalid console buffer dimensions.')
        data = (CharInfo * (width*height))()
        region = SmallRect(info.srWindow.Left, info.srWindow.Top,
                           info.srWindow.Left+width-1, info.srWindow.Top+height-1)
        if not self.kernel.ReadConsoleOutputW(self.handle, data, Coord(width,height),
                                               Coord(0,0), ctypes.byref(region)):
            raise ctypes.WinError(ctypes.get_last_error())
        return [[(data[y*width+x].UnicodeChar or ' ', data[y*width+x].Attributes)
                 for x in range(width)] for y in range(height)]

    def close(self):
        self.kernel.CloseHandle(self.handle)
        self.kernel.FreeConsole()


def record(output):
    if sys.platform != 'win32':
        raise OSError('Windows is required to capture the real console buffer.')
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont

    font_dir = Path(os.environ.get('WINDIR', r'C:\Windows'))/'Fonts'
    mono = ImageFont.truetype(str(font_dir/'consola.ttf'), 16)
    ui = ImageFont.truetype(str(font_dir/'segoeui.ttf'), 18)
    small = ImageFont.truetype(str(font_dir/'segoeui.ttf'), 14)
    # Standard Windows console colors; character attributes come from the buffer.
    palette = ('#0c0c0c','#0037da','#13a10e','#3a96dd','#c50f1f','#881798','#c19c00','#cccccc',
               '#767676','#3b78ff','#16c60c','#61d6d6','#e74856','#b4009e','#f9f1a5','#f2f2f2')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='phantom-startup-') as config_dir:
        env = os.environ.copy()
        env.pop('QT_QPA_PLATFORM', None)
        process = subprocess.Popen(['cmd.exe', '/c', 'start-windows.cmd',
                                    '--profile', str(ROOT/'native/profiles/reference-26598758.json'),
                                    '--config-dir', config_dir], cwd=ROOT, env=env,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
        encoder = capture = None
        try:
            command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                       '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1280x720',
                       '-framerate', '15', '-i', '-', '-an', '-c:v', 'libx264',
                       '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
                       '-movflags', '+faststart', str(output)]
            with tempfile.TemporaryFile() as errors:
                encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
                observed = set()
                start = time.monotonic()
                for frame in range(180):
                    time.sleep(max(0, start + frame/15 - time.monotonic()))
                    if process.poll() is not None:
                        raise RuntimeError(f'Startup process exited early: {process.returncode}')
                    if capture is None:
                        try:
                            capture = ConsoleCapture(process.pid)
                        except OSError:
                            pass
                    canvas = Image.new('RGB', (1280,720), '#16131c')
                    draw = ImageDraw.Draw(canvas)
                    draw.text((32,24), 'Phantom · Windows command startup', font=ui, fill='#f1ecf7')
                    draw.text((32,55), 'Real Windows console buffer, redrawn · no game worker started',
                              font=small, fill='#b4a9c4')
                    draw.rounded_rectangle((32,100,1248,665), radius=7, fill='#0c0c0c', outline='#574f62')
                    draw.rectangle((33,101,1247,138), fill='#25242a')
                    draw.text((50,108), 'phantom', font=small, fill='#eeeeee')
                    if capture is not None:
                        rows = capture.read()
                        for y, row in enumerate(rows):
                            text = ''.join(char for char, _ in row).rstrip()
                            if text:
                                observed.add(text)
                            # Render contiguous runs to preserve the buffer's colors.
                            x = 0
                            while x < len(row):
                                color = row[x][1] & 15
                                end = x+1
                                while end < len(row) and (row[end][1] & 15) == color:
                                    end += 1
                                draw.text((49+x*9.62,150+y*20), ''.join(c for c,_ in row[x:end]),
                                          font=mono, fill=palette[color])
                                x = end
                    encoder.stdin.write(canvas.tobytes())
                encoder.stdin.close()
                code = encoder.wait(timeout=60)
                errors.seek(0)
                text = '\n'.join(observed)
                if code or not all(msg in text for msg in ('console initialized.', 'modules initialized.', 'render initialized.')):
                    raise RuntimeError(f'Capture incomplete: encoder={code}; observed={text[:500]}; '
                                       f'{errors.read().decode(errors="replace")}')
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            if capture:
                capture.close()
            if encoder and encoder.poll() is None:
                if encoder.stdin and not encoder.stdin.closed:
                    encoder.stdin.close()
                encoder.kill()
                encoder.wait()
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=10)
    print(f'Recorded {output}: actual Windows console text redrawn, 12 seconds, no game worker.')


if __name__ == '__main__':
    try:
        record(sys.argv[1] if len(sys.argv) > 1 else 'artifacts/startup-cmd.mp4')
    except Exception as error:
        print(f'::error::{type(error).__name__}: {error}', flush=True)
        raise
