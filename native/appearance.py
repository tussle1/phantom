"""Validated GUI-only preferences; never part of worker/gameplay settings."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re

from .config import write_json

PRESETS = {
    'phantom': ('#fc589b', '#272234'),
    'midnight': ('#69b8ff', '#141e30'),
    'forest': ('#6adbb0', '#172923'),
    'graphite': ('#c4b5fd', '#202126'),
}
SCALES = (80, 90, 100, 110, 125, 150)


@dataclass
class Appearance:
    accent: str = '#fc589b'
    background: str = '#272234'
    scale: int = 100
    spacing: str = 'comfortable'
    start_expanded: bool = True


def preferences_path(directory):
    # Leading dot makes this invalid as a named gameplay config.
    return Path(directory)/'.ui-preferences.json'


def validate(document):
    if not isinstance(document, dict) or set(document) != {'version', 'appearance'} or type(document['version']) is not int or document['version'] != 1:
        raise ValueError('Expected UI preferences version 1.')
    data = document['appearance']
    if not isinstance(data, dict) or set(data) != set(asdict(Appearance())):
        raise ValueError('Unknown or missing appearance preference.')
    for key in ('accent', 'background'):
        if not isinstance(data[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', data[key]):
            raise ValueError('Colors must use #rrggbb notation.')
    if type(data['scale']) is not int or data['scale'] not in SCALES:
        raise ValueError('Unsupported interface scale.')
    if data['spacing'] not in ('compact', 'comfortable') or type(data['start_expanded']) is not bool:
        raise ValueError('Invalid layout preference.')
    return Appearance(**{**data, 'accent': data['accent'].lower(), 'background': data['background'].lower()})


def load(directory):
    path = preferences_path(directory)
    if not path.exists():
        return Appearance(), ''
    try:
        if path.stat().st_size > 8192:
            raise ValueError('UI preferences file is too large.')
        return validate(json.loads(path.read_text(encoding='utf-8'))), ''
    except (OSError, ValueError, TypeError) as error:
        return Appearance(), f'UI preferences could not be loaded; using defaults: {error}'


def save(directory, preferences):
    document = {'version': 1, 'appearance': asdict(preferences)}
    validate(document)
    write_json(preferences_path(directory), document)


def configure_scale(directory):
    """Call before QApplication. Preserve an explicitly supplied Qt scale."""
    preferences, _ = load(directory)
    os.environ.setdefault('QT_SCALE_FACTOR', str(preferences.scale/100))


def mix(a, b, fraction):
    aa = tuple(int(a[i:i+2], 16) for i in (1, 3, 5))
    bb = tuple(int(b[i:i+2], 16) for i in (1, 3, 5))
    return '#'+''.join(f'{round(x*(1-fraction)+y*fraction):02x}' for x, y in zip(aa, bb))


def palette(preferences):
    bg = preferences.background
    rgb = [int(bg[i:i+2], 16)/255 for i in (1, 3, 5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    luminance = sum(v*w for v, w in zip(linear, (.2126, .7152, .0722)))
    ink = '#f2effa' if luminance < .179 else '#201a2b'
    surface = mix(bg, '#000000' if luminance < .179 else '#ffffff', .22)
    return {'background': bg, 'surface': surface, 'ink': ink,
            'muted': mix(bg, ink, .68), 'border': mix(bg, ink, .35),
            'accent': preferences.accent, 'focus': mix(preferences.accent, ink, .35)}
