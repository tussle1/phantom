"""Phantom local companion. Python 3.11+, no third-party dependencies."""
from __future__ import annotations

import argparse
import ctypes
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
MAX_BODY = 32_768
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,39}\Z')
DEFAULTS = {
    'skeleton': True, 'health': True, 'armor': True, 'glow': False,
    'visibilityColors': True, 'teammates': False, 'sound': False,
    'spectators': True, 'bomb': True, 'radar': True, 'tracers': True,
    'hitmarker': True, 'aimMode': 'Off', 'bone': 'Head',
    'visibleFallback': True, 'smoothing': 55, 'prediction': False,
    'recoil': 'Off', 'trigger': False, 'triggerDelay': 120,
    'bunnyHop': False, 'nadeHelper': False, 'pov': 90,
    'noSpread': False, 'noFlash': False, 'noSmoke': False,
    'thirdPerson': False, 'accent': '#a995ff', 'espRange': 150,
    'aimKey': 'MouseRight', 'menuKey': 'Insert', 'triggerKey': 'AltLeft',
}
CHOICES = {'aimMode': ['Off', 'Hardlock', 'Silent', 'Humanized V2'],
           'bone': ['Head', 'Chest', 'Pelvis'], 'recoil': ['Off', 'Soft', 'Hard']}
RANGES = {'smoothing': (1, 100), 'triggerDelay': (0, 1000),
          'pov': (60, 140), 'espRange': (10, 300)}
KEY = re.compile(r'(?:Key[A-Z]|Digit[0-9]|F(?:[1-9]|1[0-2])|Mouse(?:Left|Right|Middle)|AltLeft|AltRight|ShiftLeft|ShiftRight|ControlLeft|ControlRight|Insert|Home|End|Delete|Space)\Z')


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError('Settings must contain exactly the supported keys.')
    for key, default in DEFAULTS.items():
        item = value[key]
        if type(default) is bool:
            valid = type(item) is bool
        elif key in RANGES:
            lo, hi = RANGES[key]
            valid = type(item) is int and lo <= item <= hi
        elif key in CHOICES:
            valid = isinstance(item, str) and item in CHOICES[key]
        elif key == 'accent':
            valid = isinstance(item, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', item) is not None
        else:
            valid = isinstance(item, str) and KEY.fullmatch(item) is not None
        if not valid:
            raise ValueError(f'Invalid value for {key}.')
    return dict(value)


def validate_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('Use 1–40 letters, numbers, spaces, underscores or hyphens; start with a letter or number.')
    return name


def find_cs2():
    """Enumerate Windows processes without opening or modifying the game."""
    if sys.platform != 'win32':
        return None
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), 'Process snapshot failed')
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        if not more and ctypes.get_last_error() != 18:
            raise OSError(ctypes.get_last_error(), 'Process enumeration failed')
        while more:
            if entry.szExeFile.casefold() == 'cs2.exe':
                return entry.th32ProcessID
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:
            raise OSError(ctypes.get_last_error(), 'Process enumeration failed')
        return None
    finally:
        kernel.CloseHandle(handle)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.settings = dict(DEFAULTS)
        self.active = None
        self.revision = 0

    def names(self):
        return sorted((p.stem for p in self.directory.glob('*.json')
                       if NAME.fullmatch(p.stem)), key=str.casefold)

    def path(self, name):
        return self.directory / (validate_name(name) + '.json')

    def save(self, name):
        path = self.path(name)
        with self.lock:
            fd, temporary = tempfile.mkstemp(dir=self.directory, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump({'version': 1, 'settings': self.settings}, stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self.active = name

    def load(self, name):
        path = self.path(name)
        with self.lock:
            if path.stat().st_size > MAX_BODY:
                raise ValueError('Config is too large.')
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict) or document.get('version') != 1:
                raise ValueError('Unsupported config format.')
            self.settings = validate_settings(document.get('settings'))
            self.active = name
            self.revision += 1


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, demo=False, public_origin=None):
        super().__init__(address, Handler)
        self.store = store
        self.demo = demo
        self.public_origin = public_origin
        self.token = secrets.token_urlsafe(32)
        self.detect_lock = threading.Lock()
        self.detect_time = 0.0
        self.pid = None
        self.detect_error = None

    def detection(self):
        with self.detect_lock:
            if time.monotonic() - self.detect_time > 2:
                try:
                    self.pid = find_cs2()
                    self.detect_error = None
                except OSError:
                    self.pid = None
                    self.detect_error = 'Windows process enumeration failed.'
                self.detect_time = time.monotonic()
            return self.pid, self.detect_error


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def trusted_host(self):
        host = self.headers.get('Host', '')
        port = self.server.server_address[1]
        allowed = {f'localhost:{port}', f'127.0.0.1:{port}'}
        if self.server.public_origin:
            allowed.add(urlsplit(self.server.public_origin).netloc)
        return host in allowed

    def send_data(self, status, data, content_type='application/json'):
        payload = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self' https://*.arena.ai https://arena.ai https://*.e2b.app")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not self.trusted_host():
            return self.send_data(403, {'error': 'Unrecognized host.'})
        path = urlsplit(self.path).path
        if path == '/api/state':
            pid, error = self.server.detection()
            with self.server.store.lock:
                return self.send_data(200, {
                    'mode': 'demo' if self.server.demo else 'companion',
                    'platform': sys.platform, 'pid': pid, 'detectionError': error,
                    'settings': self.server.store.settings, 'defaults': DEFAULTS,
                    'configs': self.server.store.names(), 'active': self.server.store.active,
                    'revision': self.server.store.revision,
                    'token': self.server.token,
                    'capabilities': {'processDetection': sys.platform == 'win32',
                                     'injection': False, 'gameTelemetry': False,
                                     'gameModification': False},
                })
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
        if path not in files:
            return self.send_data(404, {'error': 'Not found.'})
        filename, mime = files[path]
        self.send_data(200, (WEB / filename).read_bytes(), mime)

    def do_POST(self):
        if not self.trusted_host():
            return self.send_data(403, {'error': 'Unrecognized host.'})
        token = self.headers.get('X-Phantom-Token', '')
        if not hmac.compare_digest(token, self.server.token):
            return self.send_data(403, {'error': 'Invalid session token. Reload the page.'})
        origin = self.headers.get('Origin')
        expected = {'http://' + self.headers.get('Host', '')}
        if self.server.public_origin:
            expected.add(self.server.public_origin)
        if origin and origin not in expected:
            return self.send_data(403, {'error': 'Cross-origin write blocked.'})
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Expected application/json.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.send_data(413, {'error': 'Invalid request size.'})
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object.')
            path = urlsplit(self.path).path
            store = self.server.store
            with store.lock:
                if path not in ('/api/settings', '/api/config/save', '/api/config/load', '/api/config/delete'):
                    return self.send_data(404, {'error': 'Not found.'})
                if type(body.get('revision')) is not int or body['revision'] != store.revision:
                    return self.send_data(409, {'error': 'Settings changed in another tab. Reload to synchronize.'})
                if path == '/api/settings':
                    store.settings = validate_settings(body.get('settings'))
                    store.revision += 1
                elif path == '/api/config/save':
                    store.save(validate_name(body.get('name')))
                elif path == '/api/config/load':
                    store.load(validate_name(body.get('name')))
                elif path == '/api/config/delete':
                    name = validate_name(body.get('name'))
                    store.path(name).unlink()
                    if store.active == name:
                        store.active = None
                else:
                    return self.send_data(404, {'error': 'Not found.'})
                self.send_data(200, {'ok': True, 'revision': store.revision})
        except FileNotFoundError:
            self.send_data(404, {'error': 'Config not found.'})
        except (ValueError, UnicodeError):
            self.send_data(400, {'error': 'Invalid request or config. Check field values and name.'})
        except OSError:
            self.send_data(500, {'error': 'Local storage or connection failed.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--demo', action='store_true', help='Enable synthetic visual preview; no game connection.')
    parser.add_argument('--public-origin', help='Exact development preview origin, e.g. https://PORT-SANDBOX.e2b.app')
    parser.add_argument('--config-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home() / '.config')) / 'Phantom' / 'configs')
    args = parser.parse_args()
    if args.host not in ('127.0.0.1', 'localhost') and not args.demo:
        parser.error('Non-loopback binding is only available with --demo.')
    if args.public_origin:
        parsed = urlsplit(args.public_origin)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            parser.error('--public-origin must be an exact HTTP(S) origin without a path.')
    server = Server((args.host, args.port), Store(args.config_dir), args.demo, args.public_origin)
    print(f'Phantom: http://{args.host}:{args.port} ({"synthetic demo" if args.demo else "local companion"})', flush=True)
    print('Process detection and config storage only. No injection or game modifications.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
