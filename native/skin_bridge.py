"""Optional ctypes bridge to the compiled C++ phantom-internal-foundation library.

This bridge never injects a DLL or writes to another process. When the foundation
library is present locally, it validates ABI compatibility, inspects status, and
syncs local skin loadout preferences through the real C ABI.
"""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import sys

from .skins import MAX_SKINS, MESH_GROUPS, validate_knife_override, validate_skins

PHANTOM_OK = 0
PHANTOM_INVALID_ARGUMENT = 1
PHANTOM_STALE_DATA = 2
PHANTOM_NOT_INTEGRATED = 3
PHANTOM_NOT_FOUND = 4
PHANTOM_CAPACITY_REACHED = 5
PHANTOM_INTERNAL_ERROR = 6


class IntegrationStatus(C.Structure):
    _fields_ = [
        ('struct_size', C.c_uint32),
        ('abi_version', C.c_uint32),
        ('game_adapter_ready', C.c_uint32),
        ('live_bomb_timer_ready', C.c_uint32),
        ('cosmetic_changes_ready', C.c_uint32),
        ('reason', C.c_char * 160),
    ]


class CosmeticPreference(C.Structure):
    _fields_ = [
        ('struct_size', C.c_uint32),
        ('weapon_definition', C.c_uint32),
        ('paint_kit', C.c_uint32),
        ('seed', C.c_uint32),
        ('wear', C.c_float),
        ('stattrak', C.c_int32),
    ]


class SkinApplyReport(C.Structure):
    _fields_ = [
        ('struct_size', C.c_uint32),
        ('weapons_found', C.c_uint32),
        ('weapons_applied', C.c_uint32),
        ('weapons_restored', C.c_uint32),
        ('weapons_failed', C.c_uint32),
    ]


def library_filename():
    if sys.platform == 'win32':
        return 'phantom-internal-foundation.dll'
    if sys.platform == 'darwin':
        return 'libphantom-internal-foundation.dylib'
    return 'libphantom-internal-foundation.so'


def find_foundation_library(extra_dirs=()):
    """Search standard local package/build directories for the C++ foundation DLL/SO."""
    filename = library_filename()
    roots = [Path(d) for d in extra_dirs]
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        roots.extend((exe_dir / 'phantom-cpp', exe_dir))
    repo_root = Path(__file__).resolve().parents[1]
    roots.extend((
        repo_root / 'phantom-cpp',
        repo_root / 'build-cpp' / 'Release',
        repo_root / 'build-cpp',
    ))
    for folder in roots:
        candidate = folder / filename
        if candidate.is_file():
            return candidate
    return None


class SkinFoundationBridge:
    """Safe wrapper around the optional C++ foundation C ABI."""

    def __init__(self, library_path):
        self.path = Path(library_path)
        self._lib = C.CDLL(str(self.path))
        self._bind()
        if self.abi_version() != 1:
            raise ValueError('Unsupported phantom-internal-foundation ABI version.')

    def _bind(self):
        def bind(name, restype, *argtypes):
            fn = getattr(self._lib, name)
            fn.restype = restype
            fn.argtypes = list(argtypes)
            return fn

        self._abi_version = bind('phantom_abi_version', C.c_uint32)
        self._get_status = bind('phantom_get_integration_status', C.c_int32, C.POINTER(IntegrationStatus))
        self._set_pref = bind('phantom_set_cosmetic_preference', C.c_int32, C.POINTER(CosmeticPreference))
        self._get_pref = bind('phantom_get_cosmetic_preference', C.c_int32, C.c_uint32, C.POINTER(CosmeticPreference))
        self._remove_pref = bind('phantom_remove_cosmetic_preference', C.c_int32, C.c_uint32)
        self._list_prefs = bind('phantom_list_cosmetic_preferences', C.c_int32,
                                C.POINTER(CosmeticPreference), C.c_uint32, C.POINTER(C.c_uint32))
        self._set_name = bind('phantom_set_cosmetic_custom_name', C.c_int32, C.c_uint32, C.c_char_p)
        self._get_name = bind('phantom_get_cosmetic_custom_name', C.c_int32, C.c_uint32, C.c_char_p, C.c_uint32)
        self._set_mesh = bind('phantom_set_cosmetic_mesh_group', C.c_int32, C.c_uint32, C.c_uint64)
        self._get_mesh = bind('phantom_get_cosmetic_mesh_group', C.c_int32, C.c_uint32, C.POINTER(C.c_uint64))
        self._set_knife = bind('phantom_set_knife_override', C.c_int32, C.c_uint32)
        self._get_knife = bind('phantom_get_knife_override', C.c_int32, C.POINTER(C.c_uint32))
        self._clear = bind('phantom_clear_cosmetic_preferences', C.c_int32)
        self._runtime_available = bind('phantom_runtime_is_available', C.c_uint32)
        self._load_file = bind('phantom_runtime_load_skin_file', C.c_int32, C.c_char_p)
        self._apply_skins = bind('phantom_runtime_apply_skins', C.c_int32, C.POINTER(SkinApplyReport))
        self._restore_skins = bind('phantom_runtime_restore_skins', C.c_int32, C.POINTER(SkinApplyReport))

    def abi_version(self):
        return int(self._abi_version())

    def runtime_available(self):
        return bool(self._runtime_available())

    def status(self):
        out = IntegrationStatus()
        out.struct_size = C.sizeof(IntegrationStatus)
        code = int(self._get_status(C.byref(out)))
        if code != PHANTOM_OK:
            raise RuntimeError(f'phantom_get_integration_status failed ({code}).')
        return {
            'abi_version': int(out.abi_version),
            'game_adapter_ready': bool(out.game_adapter_ready),
            'live_bomb_timer_ready': bool(out.live_bomb_timer_ready),
            'cosmetic_changes_ready': bool(out.cosmetic_changes_ready),
            'runtime_available': self.runtime_available(),
            'reason': out.reason.decode('utf-8', errors='replace'),
        }

    def get_knife_override(self):
        value = C.c_uint32(0)
        code = int(self._get_knife(C.byref(value)))
        if code != PHANTOM_OK:
            raise RuntimeError(f'phantom_get_knife_override failed ({code}).')
        return int(value.value)

    def set_knife_override(self, knife_definition):
        clean_knife = validate_knife_override(knife_definition)
        code = int(self._set_knife(clean_knife))
        if code != PHANTOM_OK:
            raise RuntimeError(f'phantom_set_knife_override failed ({code}).')
        return clean_knife

    def sync_skins(self, skins, knife_override=0):
        clean = validate_skins(skins)
        clean_knife = validate_knife_override(knife_override)
        if int(self._clear()) != PHANTOM_OK:
            raise RuntimeError('Could not clear C++ cosmetic store.')
        for key in sorted(clean, key=int):
            weapon_id = int(key)
            entry = clean[key]
            pref = CosmeticPreference(
                struct_size=C.sizeof(CosmeticPreference),
                weapon_definition=weapon_id,
                paint_kit=entry['paint_kit'],
                seed=entry['seed'],
                wear=float(entry['wear']),
                stattrak=entry['stattrak'],
            )
            code = int(self._set_pref(C.byref(pref)))
            if code != PHANTOM_OK:
                raise RuntimeError(f'phantom_set_cosmetic_preference failed for weapon {weapon_id} ({code}).')
            name_code = int(self._set_name(weapon_id, entry['custom_name'].encode('ascii')))
            if name_code != PHANTOM_OK:
                raise RuntimeError(f'phantom_set_cosmetic_custom_name failed ({name_code}).')
            mesh_code = int(self._set_mesh(weapon_id, MESH_GROUPS[entry['mesh_group']]))
            if mesh_code != PHANTOM_OK:
                raise RuntimeError(f'phantom_set_cosmetic_mesh_group failed ({mesh_code}).')
        self.set_knife_override(clean_knife)
        return len(clean)

    def load_skin_file(self, path):
        code = int(self._load_file(str(Path(path)).encode('utf-8')))
        if code != PHANTOM_OK:
            raise ValueError(f'C++ foundation rejected skin loadout file (code {code}).')
        return self.list_preferences()

    def list_preferences(self):
        buffer = (CosmeticPreference * MAX_SKINS)()
        count = C.c_uint32(0)
        code = int(self._list_prefs(buffer, MAX_SKINS, C.byref(count)))
        if code != PHANTOM_OK:
            raise RuntimeError(f'phantom_list_cosmetic_preferences failed ({code}).')
        result = []
        for idx in range(min(int(count.value), MAX_SKINS)):
            item = buffer[idx]
            name_buf = C.create_string_buffer(64)
            self._get_name(item.weapon_definition, name_buf, 64)
            mesh = C.c_uint64(0)
            self._get_mesh(item.weapon_definition, C.byref(mesh))
            result.append({
                'weapon_definition': int(item.weapon_definition),
                'paint_kit': int(item.paint_kit),
                'seed': int(item.seed),
                'wear': float(item.wear),
                'stattrak': int(item.stattrak),
                'custom_name': name_buf.value.decode('ascii', errors='replace'),
                'mesh_group': int(mesh.value),
            })
        return result


def probe_foundation(extra_dirs=()):
    """Return a concise status dict describing whether the C++ foundation DLL is present."""
    path = find_foundation_library(extra_dirs)
    if path is None:
        return {'found': False, 'path': None, 'summary': 'C++ foundation DLL not found locally; loadout exports to .skin-loadout.json.'}
    try:
        bridge = SkinFoundationBridge(path)
        info = bridge.status()
        state = 'client.dll detected' if info['runtime_available'] else 'standby (external process)'
        return {'found': True, 'path': str(path), 'status': info,
                'summary': f'C++ foundation ABI v{info["abi_version"]} verified · {state}.'}
    except (OSError, ValueError, RuntimeError, AttributeError) as error:
        return {'found': True, 'path': str(path), 'summary': f'C++ foundation check failed: {error}'}
