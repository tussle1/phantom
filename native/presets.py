"""Built-in starting points, not live-tested or anti-cheat-safe profiles."""
from dataclasses import asdict

from .config import Config, validate_config

# Every preset starts from defaults, then applies these explicit differences.
# Aim/trigger enabled profiles must be explicitly selected and confirmed in GUI.
PRESETS = {
    'defaults': ('Original defaults. Aim, trigger and bunny hop are off.', {}),
    'esp minimal': ('Visuals only: health, 100 m range. No skeleton, armor, radar or spectators.',
                    {'skeleton': False, 'armor': False, 'radar': False,
                     'spectators': False, 'max_distance_m': 100.0}),
    'esp detailed': ('Visuals only: skeleton, health, armor, radar and spectators; 250 m range.',
                     {'max_distance_m': 250.0}),
    'smooth aim practice': ('Enables hold-key smooth aim: 2 degree FOV, 200 ms smoothing, 60 degrees/s, chest. ESP off.',
                            {'esp': False, 'radar': False, 'spectators': False, 'aim': 'smooth',
                             'aim_fov': 2.0, 'smooth_time': .2, 'max_aim_speed': 60.0, 'priority_bone': 'chest'}),
    'combined practice': ('Enables hold-key smooth aim plus detailed ESP: 3 degree FOV, 150 ms smoothing, 75 degrees/s, chest; 150 m range.',
                          {'aim': 'smooth', 'smooth_time': .15, 'max_aim_speed': 75.0, 'priority_bone': 'chest'}),
    'trigger practice': ('Enables hold-key trigger with 250 ms delay; aim and bunny hop off. Health-only ESP, 100 m range.',
                         {'trigger': True, 'trigger_delay_ms': 250.0, 'skeleton': False,
                          'armor': False, 'radar': False, 'spectators': False, 'max_distance_m': 100.0}),
}
PRESERVE = ('keys', 'bones', 'mouse_yaw', 'mouse_pitch', 'skins')


def preset_config(name, current=None):
    if name not in PRESETS:
        raise ValueError('Unknown built-in preset.')
    settings = asdict(Config())
    settings.update(PRESETS[name][1])
    if current is not None:
        old = asdict(current)
        settings.update({key: old[key] for key in PRESERVE})
    return validate_config({'version': 1, 'settings': settings})


def preset_document(name):
    return {'version': 1, 'settings': asdict(preset_config(name))}


def preset_filename(name):
    if name not in PRESETS:
        raise ValueError('Unknown built-in preset.')
    return name.replace(' ', '-')+'.json'
