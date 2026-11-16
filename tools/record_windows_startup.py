"""Capture Phantom's actual Windows console and panel, without starting the worker.

Windows, Python 3.11+, PySide6 Essentials, Pillow 11.2.1 and imageio-ffmpeg 0.6.0.
The two real application windows are composited onto a canvas for legibility.
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


def record(output):
    if sys.platform != 'win32':
        raise OSError('Windows is required to record the real startup windows.')
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageStat

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND

    font_path = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'segoeui.ttf')
    font = ImageFont.truetype(font_path, 20)
    small = ImageFont.truetype(font_path, 15)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='phantom-startup-') as config_dir:
        env = os.environ.copy()
        env.pop('QT_QPA_PLATFORM', None)
        process = subprocess.Popen(['cmd.exe', '/c', 'start-windows.cmd',
                                    '--profile', str(ROOT/'native/profiles/reference-26598758.json'),
                                    '--config-dir', config_dir], cwd=ROOT, env=env,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
        encoder = None
        try:
            command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                       '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1280x720',
                       '-framerate', '15', '-i', '-', '-an', '-c:v', 'libx264',
                       '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
                       '-movflags', '+faststart', str(output)]
            with tempfile.TemporaryFile() as errors:
                encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
                console_seen = panel_seen = False
                start = time.monotonic()
                for frame in range(180):
                    due = start + frame/15
                    time.sleep(max(0, due-time.monotonic()))
                    if process.poll() is not None:
                        raise RuntimeError(f'Startup process exited early: {process.returncode}')
                    canvas = Image.new('RGB', (1280,720), '#16131c')
                    draw = ImageDraw.Draw(canvas)
                    draw.text((25,18), 'Phantom · Windows command startup', font=font, fill='#f1ecf7')
                    draw.text((25,49), 'Actual windows, composited for clarity · no game worker started', font=small, fill='#b4a9c4')
                    for title, box, is_console in (
                        ('phantom', (25,112,625,600), True),
                        ('phantom — native control panel', (650,88,1255,678), False),
                    ):
                        hwnd = user32.FindWindowW(None, title)
                        if not hwnd:
                            continue
                        try:
                            image = ImageGrab.grab(window=hwnd).convert('RGB')
                        except OSError:
                            continue
                        # Blank captures are not evidence of a real visible window.
                        if image.width < 100 or image.height < 100 or max(ImageStat.Stat(image).stddev) < 3:
                            continue
                        image.thumbnail((box[2]-box[0],box[3]-box[1]), Image.Resampling.LANCZOS)
                        canvas.paste(image,(box[0],box[1]))
                        if is_console:
                            console_seen = True
                        else:
                            panel_seen = True
                    if not console_seen:
                        draw.text((25,92),'Launching start-windows.cmd…',font=small,fill='#b4a9c4')
                    encoder.stdin.write(canvas.tobytes())
                encoder.stdin.close()
                code = encoder.wait(timeout=60)
                errors.seek(0)
                if code or not console_seen or not panel_seen:
                    raise RuntimeError(f'Capture incomplete: console={console_seen} panel={panel_seen}; '
                                       f'encoder={code}; {errors.read().decode(errors="replace")}')
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            if encoder and encoder.poll() is None:
                if encoder.stdin and not encoder.stdin.closed:
                    encoder.stdin.close()
                encoder.kill()
                encoder.wait()
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=10)
    print(f'Recorded {output}: actual Windows console and GUI, 12 seconds, no game worker.')


if __name__ == '__main__':
    try:
        record(sys.argv[1] if len(sys.argv) > 1 else 'artifacts/startup-cmd.mp4')
    except Exception as error:
        print(f'::error::{type(error).__name__}: {error}', flush=True)
        raise
