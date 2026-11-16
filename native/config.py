"""Strict native-only configurations, separate from the legacy dashboard."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .hotkeys import keys_conflict
from .esp_style import DEFAULT_STYLE
from .skins import validate_skins


@dataclass
class Config:
    esp_style: dict = field(default_factory=lambda: dict(DEFAULT_STYLE))
    esp: bool = True
    skeleton: bool = True
    health: bool = True
    armor: bool = True
    teammates: bool = False
    radar: bool = True
    spectators: bool = True
    aim: str = 'off'
    aim_fov: float = 3.0
    aim_draw_fov: bool = False
    catalyst_smoothing: float = 5.0
    smooth_time: float = 0.12
    max_aim_speed: float = 90.0
    prediction_ms: float = 0.0
    trigger: bool = False
    trigger_delay_ms: float = 150.0
    bunny_hop: bool = False
    skin_changer: bool = False
    skins: dict = field(default_factory=dict)
    max_distance_m: float = 150.0
    mouse_yaw: float = 0.022
    mouse_pitch: float = 0.022
    priority_bone: str = 'head'
    bones: dict = field(default_factory=lambda: {'head': 6, 'neck': 5, 'chest': 4, 'pelvis': 0,
        'left_shoulder': 8, 'left_elbow': 9, 'left_hand': 10,
        'right_shoulder': 13, 'right_elbow': 14, 'right_hand': 15,
        'left_knee': 23, 'left_foot': 24, 'right_knee': 26, 'right_foot': 27})
    keys: dict = field(default_factory=lambda: {'aim_hold': 0x02, 'trigger_hold': 0x12,
        'jump_hold': 0x20, 'menu_toggle': 0xA1, 'esp_toggle': 0x75, 'aim_toggle': 0x76,
        'trigger_toggle': 0x77, 'radar_toggle': 0x74, 'reload': 0x78, 'save': 0x79, 'exit': 0x23})


FLOATS = {'catalyst_smoothing': (1, 100), 'aim_fov': (0.1, 30), 'smooth_time': (0.02, 2), 'max_aim_speed': (1, 360),
          'prediction_ms': (0, 250), 'trigger_delay_ms': (0, 2000),
          'max_distance_m': (1, 1000), 'mouse_yaw': (0.001, 1), 'mouse_pitch': (0.001, 1)}
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,39}\Z')


def validate_config(document):
    if not isinstance(document, dict) or type(document.get('version')) is not int or document.get('version') != 1 or set(document) != {'version', 'settings'}:
        raise ValueError('Expected native config version 1.')
    settings = document['settings']
    defaults = asdict(Config())
    # Upgrade older v1 settings only for explicitly introduced optional fields.
    if isinstance(settings, dict) and not (set(settings) - set(defaults)):
        missing = set(defaults) - set(settings)
        if missing <= {'esp_style', 'aim_draw_fov', 'catalyst_smoothing', 'skin_changer', 'skins'}:
            settings = {**settings, **{key: defaults[key] for key in missing}}
    if not isinstance(settings, dict) or set(settings) != set(defaults):
        raise ValueError('Unknown or missing native setting; dashboard configs are not native configs.')
    for key, default in defaults.items():
        value = settings[key]
        if type(default) is bool and type(value) is not bool:
            raise ValueError(f'{key} must be a boolean.')
        if key in FLOATS:
            lo, hi = FLOATS[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f'{key} must be between {lo} and {hi}.')
            if key == 'catalyst_smoothing' and value != int(value):
                raise ValueError('catalyst_smoothing must be a whole number.')
    style = settings['esp_style']
    # Upgrade previously saved v1 ESP styles without modifying the caller's data.
    if isinstance(style, dict) and set(style) == set(DEFAULT_STYLE)-{'box_style'}:
        style = {**style, 'box_style': DEFAULT_STYLE['box_style']}
        settings = {**settings, 'esp_style': style}
    if not isinstance(style, dict) or set(style) != set(DEFAULT_STYLE):
        raise ValueError('Expected the complete ESP style.')
    for key, default in DEFAULT_STYLE.items():
        value = style[key]
        if key.endswith('_color'):
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value) or value.lower() == '#000000':
                raise ValueError('ESP colors require #rrggbb; pure black is the overlay transparency key.')
        elif key == 'box_style':
            if value not in ('full', 'corner') or not isinstance(value, str):
                raise ValueError('ESP box style must be full or corner.')
        elif key == 'line_width':
            if type(value) is not int or not 1 <= value <= 4:
                raise ValueError('ESP line width must be 1–4.')
        elif type(value) is not bool:
            raise ValueError('ESP visibility options must be booleans.')
    if settings['aim'] not in ('off', 'hardlock', 'smooth', 'catalyst'):
        raise ValueError('aim must be off, hardlock, smooth, or catalyst. Silent aim is not implemented.')
    if not isinstance(settings['bones'], dict) or set(settings['bones']) != set(defaults['bones']):
        raise ValueError('Expected the complete named bone map.')
    if any(type(v) is not int or not 0 <= v <= 255 for v in settings['bones'].values()):
        raise ValueError('Bone indices must be integers in 0–255.')
    if settings['priority_bone'] not in ('head', 'neck', 'chest', 'pelvis'):
        raise ValueError('Invalid priority bone.')
    if isinstance(settings['keys'], dict) and set(settings['keys']) == set(defaults['keys'])-{'menu_toggle'}:
        # Upgrade old v1 configs without changing any pre-existing binding. Prefer
        # Right Shift, but do not silently assign an already-used modifier alias.
        keys = dict(settings['keys'])
        if any(type(v) is not int or not 1 <= v <= 254 for v in keys.values()):
            raise ValueError('Key bindings must be Windows virtual-key codes 1-254.')
        candidates = (0xA1, 0x2D, 0x7B, 0x7A, 0x24)
        available = next((vk for vk in candidates if not any(keys_conflict(vk, old) for old in keys.values())), None)
        if available is None:
            raise ValueError('No free menu key for this legacy config. Add a unique menu_toggle binding.')
        settings = {**settings, 'keys': {**keys, 'menu_toggle': available}}
    if not isinstance(settings['keys'], dict) or set(settings['keys']) != set(defaults['keys']):
        raise ValueError('Expected all native key bindings.')
    if any(type(v) is not int or not 1 <= v <= 254 for v in settings['keys'].values()):
        raise ValueError('Key bindings must be Windows virtual-key codes 1–254.')
    toggles = [v for k, v in settings['keys'].items() if not k.endswith('_hold')]
    holds = [v for k, v in settings['keys'].items() if k.endswith('_hold')]
    if any(keys_conflict(a, b) for i, a in enumerate(toggles) for b in toggles[i+1:]+holds):
        raise ValueError('Toggle/action key bindings must be unique and separate from hold keys.')
    skins = validate_skins(settings['skins'])
    return Config(**{**settings, 'keys': dict(settings['keys']), 'bones': dict(settings['bones']),
                     'esp_style': dict(settings['esp_style']), 'skins': skins})


def config_path(directory, name):
    if not isinstance(name, str) or not NAME.fullmatch(name) or name.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))} or name.endswith(' '):
        raise ValueError('Invalid native config name. Use 1–40 letters, digits, spaces, _ or -; no Windows device names.')
    return Path(directory) / (name + '.json')


def write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_config(path, config):
    document = {'version': 1, 'settings': asdict(config)}
    validate_config(document)
    write_json(path, document)


def load_config(path):
    path = Path(path)
    if path.stat().st_size > 32768:
        raise ValueError('Native config is too large.')
    return validate_config(json.loads(path.read_text(encoding='utf-8')))
