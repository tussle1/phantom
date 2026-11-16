"""Toolkit-independent, validated settings model for the native control panel."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .config import Config, config_path, load_config, save_config, validate_config
from .presets import preset_config
from .skins import STARTER_LOADOUTS, export_loadout, validate_skin_entry

# label, config key, display multiplier, min, max, decimals, suffix
SLIDERS = (
    ('Aim FOV', 'aim_fov', 1, .1, 30, 1, '°'),
    ('Smoothing', 'smooth_time', 1000, 20, 2000, 0, 'ms'),
    ('Prediction', 'prediction_ms', 1, 0, 250, 0, 'ms'),
    ('Shot delay', 'trigger_delay_ms', 1, 0, 2000, 0, 'ms'),
)


class SettingsModel:
    def __init__(self, directory, name='default'):
        self.directory = Path(directory)
        self.name = name
        path = config_path(self.directory, name)
        self.config = load_config(path) if path.exists() else Config()
        self.revision = 0

    @property
    def path(self):
        return config_path(self.directory, self.name)

    def document(self):
        return {'version': 1, 'settings': asdict(self.config)}

    def set(self, key, value):
        settings = asdict(self.config)
        if key not in settings:
            raise ValueError('Unknown native setting.')
        settings[key] = value
        config = validate_config({'version': 1, 'settings': settings})
        self.config = config
        self.revision += 1

    def set_key(self, key, value):
        keys = dict(self.config.keys)
        if key not in keys:
            raise ValueError('Unknown key binding.')
        keys[key] = value
        self.set('keys', keys)

    def set_aim_enabled(self, enabled):
        self.set('aim', 'smooth' if enabled and self.config.aim == 'off' else self.config.aim if enabled else 'off')

    def set_skin(self, weapon_definition, entry):
        if type(weapon_definition) is not int or not 1 <= weapon_definition <= 65535:
            raise ValueError('Weapon definition must be an integer in 1-65535.')
        skins = {k: dict(v) for k, v in self.config.skins.items()}
        skins[str(weapon_definition)] = validate_skin_entry(entry)
        self.set('skins', skins)

    def remove_skin(self, weapon_definition):
        if type(weapon_definition) is not int or not 1 <= weapon_definition <= 65535:
            raise ValueError('Weapon definition must be an integer in 1-65535.')
        key = str(weapon_definition)
        if key not in self.config.skins:
            return False
        skins = {k: dict(v) for k, v in self.config.skins.items() if k != key}
        self.set('skins', skins)
        return True

    def clear_skins(self):
        if not self.config.skins:
            return
        self.set('skins', {})

    def apply_skin_pack(self, name):
        if name not in STARTER_LOADOUTS:
            raise ValueError('Unknown starter skin pack.')
        pack = {k: dict(v) for k, v in STARTER_LOADOUTS[name].items()}
        self.set('skins', pack)

    def export_skins(self):
        return export_loadout(self.directory, self.config.skin_changer, self.config.skins)

    def reset(self, key):
        self.set(key, asdict(Config())[key])

    def save(self, name=None):
        name = name if name is not None else self.name
        path = config_path(self.directory, name)
        save_config(path, self.config)
        self.name = name

    def load(self, name):
        config = load_config(config_path(self.directory, name))
        self.config, self.name = config, name
        self.revision += 1

    def apply_preset(self, name):
        config = preset_config(name, self.config)
        self.config = config
        self.revision += 1

    def names(self):
        if not self.directory.exists():
            return []
        result = []
        for path in self.directory.glob('*.json'):
            try:
                config_path(self.directory, path.stem)
                result.append(path.stem)
            except ValueError:
                continue
        return sorted(result, key=str.casefold)

    def accept_runtime(self, settings, revision):
        if type(revision) is not int or revision < self.revision:
            return False
        config = validate_config({'version': 1, 'settings': settings})
        self.config, self.revision = config, revision
        return True
