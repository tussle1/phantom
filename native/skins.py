"""Local-only CS2 weapon skin catalog, validation, and loadout export.

Stores and exports client-side cosmetic preferences only. Never alters Steam
inventory ownership or makes skins visible to other players.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_SKINS = 32
MAX_PAINT_KIT = 0x7FFFFFFF
MAX_SEED = 1000
MAX_STATTRAK = 999999
MAX_CUSTOM_NAME = 32

MESH_GROUPS = {'auto': 0, 'modern': 1, 'legacy': 2}
WEAPON_KEY_RE = re.compile(r'[1-9][0-9]{0,4}\Z')

RARITY_COLORS = {
    'Default': '#8c83a6',
    'Mil-Spec': '#4b69ff',
    'Restricted': '#8847ff',
    'Classified': '#d32ce6',
    'Covert': '#eb4b4b',
    'Contraband': '#e4ae39',
}

# (label, short code, min inclusive, max inclusive, preset float, swatch hex)
WEAR_TIERS = (
    ('Factory New', 'FN', 0.0, 0.07, 0.001, '#55dc8c'),
    ('Minimal Wear', 'MW', 0.07, 0.15, 0.08, '#45c7d6'),
    ('Field-Tested', 'FT', 0.15, 0.38, 0.18, '#f0c85a'),
    ('Well-Worn', 'WW', 0.38, 0.45, 0.40, '#f08c4a'),
    ('Battle-Scarred', 'BS', 0.45, 1.0, 0.65, '#e8586b'),
)


@dataclass(frozen=True)
class WeaponDef:
    definition: int
    name: str
    category: str


@dataclass(frozen=True)
class PaintKit:
    paint_kit: int
    name: str
    rarity: str
    swatches: tuple[str, str, str]
    weapons: tuple[int, ...]
    mesh_group: str = 'auto'


WEAPON_CATEGORIES = ('All', 'Rifles', 'Snipers', 'Pistols', 'SMGs', 'Heavy')

WEAPONS = (
    # Rifles
    WeaponDef(7, 'AK-47', 'Rifles'),
    WeaponDef(16, 'M4A4', 'Rifles'),
    WeaponDef(60, 'M4A1-S', 'Rifles'),
    WeaponDef(13, 'Galil AR', 'Rifles'),
    WeaponDef(10, 'FAMAS', 'Rifles'),
    WeaponDef(8, 'AUG', 'Rifles'),
    WeaponDef(39, 'SG 553', 'Rifles'),
    # Snipers
    WeaponDef(9, 'AWP', 'Snipers'),
    WeaponDef(40, 'SSG 08', 'Snipers'),
    WeaponDef(38, 'SCAR-20', 'Snipers'),
    WeaponDef(11, 'G3SG1', 'Snipers'),
    # Pistols
    WeaponDef(4, 'Glock-18', 'Pistols'),
    WeaponDef(61, 'USP-S', 'Pistols'),
    WeaponDef(32, 'P2000', 'Pistols'),
    WeaponDef(1, 'Desert Eagle', 'Pistols'),
    WeaponDef(36, 'P250', 'Pistols'),
    WeaponDef(3, 'Five-SeveN', 'Pistols'),
    WeaponDef(30, 'Tec-9', 'Pistols'),
    WeaponDef(63, 'CZ75-Auto', 'Pistols'),
    WeaponDef(2, 'Dual Berettas', 'Pistols'),
    WeaponDef(64, 'R8 Revolver', 'Pistols'),
    # SMGs
    WeaponDef(17, 'MAC-10', 'SMGs'),
    WeaponDef(34, 'MP9', 'SMGs'),
    WeaponDef(33, 'MP7', 'SMGs'),
    WeaponDef(23, 'MP5-SD', 'SMGs'),
    WeaponDef(24, 'UMP-45', 'SMGs'),
    WeaponDef(19, 'P90', 'SMGs'),
    WeaponDef(26, 'PP-Bizon', 'SMGs'),
    # Heavy
    WeaponDef(35, 'Nova', 'Heavy'),
    WeaponDef(25, 'XM1014', 'Heavy'),
    WeaponDef(27, 'MAG-7', 'Heavy'),
    WeaponDef(29, 'Sawed-Off', 'Heavy'),
    WeaponDef(14, 'M249', 'Heavy'),
    WeaponDef(28, 'Negev', 'Heavy'),
)
WEAPON_BY_ID = {weapon.definition: weapon for weapon in WEAPONS}

# Curated real CS2 paint kit definitions; users can also specify any custom kit ID.
PAINT_KITS = (
    PaintKit(0, 'Vanilla', 'Default', ('#3a3548', '#524b63', '#6b637f'), (), 'auto'),
    # AK-47
    PaintKit(282, 'Redline', 'Classified', ('#1f1f24', '#d62828', '#3c3c44'), (7,), 'legacy'),
    PaintKit(180, 'Fire Serpent', 'Covert', ('#2b463c', '#76a05e', '#d66832'), (7,), 'legacy'),
    PaintKit(302, 'Vulcan', 'Covert', ('#1b263b', '#38a3d1', '#eef4f8'), (7,), 'legacy'),
    PaintKit(44, 'Case Hardened', 'Classified', ('#2a62b6', '#d8a642', '#7e62a0'), (7, 3, 17), 'legacy'),
    PaintKit(422, 'Elite Build', 'Mil-Spec', ('#26262a', '#4a4a52', '#e09f3e'), (7,), 'legacy'),
    PaintKit(524, 'Fuel Injector', 'Covert', ('#f4c430', '#3d3d42', '#d9a404'), (7,), 'legacy'),
    PaintKit(639, 'Bloodsport', 'Covert', ('#d91e36', '#f2f2f2', '#26262e'), (7,), 'legacy'),
    PaintKit(675, 'The Empress', 'Covert', ('#c1121f', '#e5b84b', '#1d3557'), (7,), 'legacy'),
    PaintKit(707, 'Neon Rider', 'Covert', ('#fc589b', '#2ec4e6', '#5e2b97'), (7,), 'legacy'),
    PaintKit(724, 'Wild Lotus', 'Covert', ('#2d6a4f', '#f4722b', '#e9c46a'), (7,), 'legacy'),
    PaintKit(801, 'Asiimov', 'Covert', ('#f5f5f5', '#f26419', '#252429'), (7,), 'legacy'),
    PaintKit(1035, 'Slate', 'Restricted', ('#1c1c21', '#2d2d35', '#42424d'), (7,), 'legacy'),
    PaintKit(1171, 'Inheritance', 'Covert', ('#f0f4f8', '#2a5ca8', '#d4af37'), (7,), 'modern'),
    # M4A4
    PaintKit(309, 'Howl', 'Contraband', ('#1f1c1d', '#d92626', '#f59e0b'), (16,), 'legacy'),
    PaintKit(255, 'Asiimov', 'Covert', ('#f5f5f5', '#f26419', '#252429'), (16,), 'legacy'),
    PaintKit(400, 'Dragon King', 'Classified', ('#283a75', '#d93848', '#68b0ab'), (16,), 'legacy'),
    PaintKit(588, 'Desolate Space', 'Classified', ('#1b1f3b', '#3a86ff', '#9b5de5'), (16,), 'legacy'),
    PaintKit(695, 'Neo-Noir', 'Covert', ('#1f1c2e', '#ec4899', '#38bdf8'), (16,), 'legacy'),
    PaintKit(844, 'The Emperor', 'Covert', ('#1b3b6f', '#e5b84b', '#4682b4'), (16,), 'legacy'),
    PaintKit(1228, 'Temukau', 'Covert', ('#f2f5f9', '#ec4899', '#3b82f6'), (16,), 'modern'),
    # M4A1-S
    PaintKit(326, 'Knight', 'Classified', ('#1d1d22', '#35353d', '#c9a227'), (60,), 'legacy'),
    PaintKit(360, 'Cyrex', 'Covert', ('#1b1b20', '#d92638', '#f2f2f5'), (60,), 'legacy'),
    PaintKit(430, 'Hyper Beast', 'Covert', ('#182233', '#ec4899', '#22d3ee'), (60,), 'legacy'),
    PaintKit(497, 'Golden Coil', 'Covert', ('#1e1d20', '#d4af37', '#8c6d1f'), (60,), 'legacy'),
    PaintKit(644, 'Decimator', 'Classified', ('#24163d', '#fc589b', '#2ec4e6'), (60,), 'legacy'),
    PaintKit(984, 'Printstream', 'Covert', ('#f5f5f7', '#d8d4e8', '#1c1b22'), (60,), 'legacy'),
    PaintKit(1017, 'Blue Phosphor', 'Classified', ('#0a2472', '#1d4ed8', '#38bdf8'), (60,), 'legacy'),
    # AWP
    PaintKit(344, 'Dragon Lore', 'Covert', ('#c9972e', '#8c1c13', '#2f3e2e'), (9,), 'legacy'),
    PaintKit(51, 'Lightning Strike', 'Covert', ('#3b1c63', '#8b5cf6', '#e0e7ff'), (9,), 'legacy'),
    PaintKit(259, 'Redline', 'Classified', ('#1f1f24', '#d62828', '#3c3c44'), (9,), 'legacy'),
    PaintKit(279, 'Asiimov', 'Covert', ('#f5f5f5', '#f26419', '#252429'), (9,), 'legacy'),
    PaintKit(395, 'Man-o-war', 'Covert', ('#172554', '#1e3a8a', '#d4af37'), (9,), 'legacy'),
    PaintKit(446, 'Medusa', 'Covert', ('#0f2942', '#1d6f8a', '#64dfdf'), (9,), 'legacy'),
    PaintKit(475, 'Hyper Beast', 'Covert', ('#1b1b2f', '#e11d48', '#06b6d4'), (9,), 'legacy'),
    PaintKit(662, 'Oni Taiji', 'Covert', ('#3c1b5c', '#e63946', '#f4a261'), (9,), 'legacy'),
    PaintKit(736, 'The Prince', 'Covert', ('#7f1d1d', '#dc2626', '#e5b84b'), (9,), 'legacy'),
    PaintKit(756, 'Gungnir', 'Covert', ('#0b4f6c', '#38bdf8', '#e0f2fe'), (9,), 'legacy'),
    PaintKit(803, 'Neo-Noir', 'Covert', ('#1f1c2e', '#ec4899', '#38bdf8'), (9,), 'legacy'),
    PaintKit(887, 'Containment Breach', 'Covert', ('#1a3c2b', '#84cc16', '#facc15'), (9,), 'legacy'),
    PaintKit(917, 'Wildfire', 'Covert', ('#1f1c1d', '#ea580c', '#facc15'), (9,), 'legacy'),
    PaintKit(1026, 'Fade', 'Covert', ('#8b5cf6', '#ec4899', '#f59e0b'), (9,), 'legacy'),
    PaintKit(1170, 'Chrome Cannon', 'Covert', ('#334155', '#a855f7', '#38bdf8'), (9,), 'modern'),
    # Desert Eagle
    PaintKit(37, 'Blaze', 'Restricted', ('#1c1b20', '#ea580c', '#facc15'), (1,), 'legacy'),
    PaintKit(711, 'Code Red', 'Covert', ('#b91c1c', '#f5f5f5', '#27272a'), (1,), 'legacy'),
    PaintKit(757, 'Emerald Jormungandr', 'Restricted', ('#064e3b', '#10b981', '#a7f3d0'), (1,), 'legacy'),
    PaintKit(962, 'Printstream', 'Covert', ('#f5f5f7', '#d8d4e8', '#1c1b22'), (1,), 'legacy'),
    PaintKit(1090, 'Ocean Drive', 'Covert', ('#ec4899', '#f97316', '#06b6d4'), (1,), 'legacy'),
    # Glock-18
    PaintKit(38, 'Fade', 'Restricted', ('#8b5cf6', '#ec4899', '#f59e0b'), (4,), 'legacy'),
    PaintKit(353, 'Water Elemental', 'Classified', ('#dc2626', '#38bdf8', '#1d4ed8'), (4,), 'legacy'),
    PaintKit(957, 'Bullet Queen', 'Covert', ('#facc15', '#ec4899', '#1f1c2e'), (4,), 'legacy'),
    PaintKit(988, 'Neo-Noir', 'Classified', ('#1f1c2e', '#ec4899', '#38bdf8'), (4,), 'legacy'),
    PaintKit(1119, 'Gamma Doppler', 'Covert', ('#064e3b', '#10b981', '#22d3ee'), (4,), 'legacy'),
    # USP-S
    PaintKit(313, 'Orion', 'Classified', ('#1e1e24', '#f97316', '#facc15'), (61,), 'legacy'),
    PaintKit(504, 'Kill Confirmed', 'Covert', ('#7f1d1d', '#ef4444', '#e5e7eb'), (61,), 'legacy'),
    PaintKit(653, 'Neo-Noir', 'Covert', ('#1f1c2e', '#ec4899', '#38bdf8'), (61,), 'legacy'),
    PaintKit(705, 'Cortex', 'Classified', ('#1f1f26', '#ec4899', '#94a3b8'), (61,), 'legacy'),
    PaintKit(1142, 'Printstream', 'Covert', ('#f5f5f7', '#d8d4e8', '#1c1b22'), (61,), 'legacy'),
    # Other iconic weapons
    PaintKit(222, 'Blood in the Water', 'Covert', ('#334155', '#dc2626', '#94a3b8'), (40,), 'legacy'),
    PaintKit(624, 'Dragonfire', 'Covert', ('#1e3a8a', '#f97316', '#38bdf8'), (40,), 'legacy'),
    PaintKit(379, 'Cerberus', 'Restricted', ('#27272a', '#84cc16', '#facc15'), (13,), 'legacy'),
    PaintKit(919, 'Commemoration', 'Covert', ('#d4af37', '#78350f', '#fde68a'), (10,), 'legacy'),
    PaintKit(433, 'Neon Rider', 'Covert', ('#fc589b', '#2ec4e6', '#5e2b97'), (17,), 'legacy'),
    PaintKit(556, 'Primal Saber', 'Classified', ('#1f1f26', '#22d3ee', '#f5f5f5'), (24,), 'legacy'),
)

DEFAULT_SKIN_ENTRY = {
    'paint_kit': 0,
    'seed': 0,
    'wear': 0.001,
    'stattrak': -1,
    'custom_name': '',
    'mesh_group': 'auto',
}

STARTER_LOADOUTS = {
    'phantom neon': {
        '7': {'paint_kit': 707, 'seed': 120, 'wear': 0.008, 'stattrak': 1337, 'custom_name': 'phantom', 'mesh_group': 'legacy'},
        '16': {'paint_kit': 695, 'seed': 42, 'wear': 0.015, 'stattrak': 420, 'custom_name': '', 'mesh_group': 'legacy'},
        '60': {'paint_kit': 644, 'seed': 88, 'wear': 0.01, 'stattrak': 512, 'custom_name': '', 'mesh_group': 'legacy'},
        '9': {'paint_kit': 803, 'seed': 77, 'wear': 0.02, 'stattrak': 999, 'custom_name': 'phantom', 'mesh_group': 'legacy'},
        '1': {'paint_kit': 1090, 'seed': 15, 'wear': 0.01, 'stattrak': 300, 'custom_name': '', 'mesh_group': 'legacy'},
        '4': {'paint_kit': 988, 'seed': 25, 'wear': 0.02, 'stattrak': 250, 'custom_name': '', 'mesh_group': 'legacy'},
        '61': {'paint_kit': 653, 'seed': 33, 'wear': 0.02, 'stattrak': 350, 'custom_name': '', 'mesh_group': 'legacy'},
        '17': {'paint_kit': 433, 'seed': 99, 'wear': 0.01, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
    },
    'classic covert': {
        '7': {'paint_kit': 282, 'seed': 0, 'wear': 0.15, 'stattrak': 1000, 'custom_name': '', 'mesh_group': 'legacy'},
        '16': {'paint_kit': 309, 'seed': 0, 'wear': 0.01, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
        '60': {'paint_kit': 984, 'seed': 0, 'wear': 0.01, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
        '9': {'paint_kit': 344, 'seed': 0, 'wear': 0.008, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
        '1': {'paint_kit': 37, 'seed': 0, 'wear': 0.005, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
        '4': {'paint_kit': 38, 'seed': 0, 'wear': 0.005, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
        '61': {'paint_kit': 504, 'seed': 0, 'wear': 0.01, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
    },
    'clean stealth': {
        '7': {'paint_kit': 1035, 'seed': 0, 'wear': 0.005, 'stattrak': 500, 'custom_name': '', 'mesh_group': 'legacy'},
        '60': {'paint_kit': 984, 'seed': 0, 'wear': 0.005, 'stattrak': 500, 'custom_name': '', 'mesh_group': 'legacy'},
        '9': {'paint_kit': 1170, 'seed': 0, 'wear': 0.005, 'stattrak': 500, 'custom_name': '', 'mesh_group': 'modern'},
        '1': {'paint_kit': 962, 'seed': 0, 'wear': 0.005, 'stattrak': 250, 'custom_name': '', 'mesh_group': 'legacy'},
        '61': {'paint_kit': 1142, 'seed': 0, 'wear': 0.005, 'stattrak': 250, 'custom_name': '', 'mesh_group': 'legacy'},
        '4': {'paint_kit': 1119, 'seed': 412, 'wear': 0.005, 'stattrak': -1, 'custom_name': '', 'mesh_group': 'legacy'},
    },
}


def wear_tier(wear):
    """Return (label, short_code, swatch_color) for a normalized wear float [0, 1]."""
    value = max(0.0, min(1.0, float(wear)))
    for label, short, lo, hi, _, color in WEAR_TIERS:
        if lo <= value < hi or (hi == 1.0 and value <= hi):
            return label, short, color
    return WEAR_TIERS[-1][0], WEAR_TIERS[-1][1], WEAR_TIERS[-1][5]


def weapon_name(definition):
    weapon = WEAPON_BY_ID.get(int(definition))
    return weapon.name if weapon else f'Weapon #{int(definition)}'


def kits_for_weapon(definition):
    """Return curated paint kits for a weapon, starting with Vanilla then weapon matches."""
    weapon_id = int(definition)
    exact = [kit for kit in PAINT_KITS if kit.paint_kit != 0 and weapon_id in kit.weapons]
    return [PAINT_KITS[0], *exact]


def kit_by_id(paint_kit, definition=None):
    """Look up a PaintKit by ID, preferring one tagged for the given weapon."""
    kit_id = int(paint_kit)
    if definition is not None:
        weapon_id = int(definition)
        for kit in PAINT_KITS:
            if kit.paint_kit == kit_id and weapon_id in kit.weapons:
                return kit
    for kit in PAINT_KITS:
        if kit.paint_kit == kit_id:
            return kit
    return None


def validate_skin_entry(entry):
    if not isinstance(entry, dict) or set(entry) != set(DEFAULT_SKIN_ENTRY):
        raise ValueError('Skin entry must specify paint_kit, seed, wear, stattrak, custom_name, and mesh_group.')
    paint_kit = entry['paint_kit']
    if type(paint_kit) is not int or not 0 <= paint_kit <= MAX_PAINT_KIT:
        raise ValueError(f'Skin paint_kit must be an integer in 0-{MAX_PAINT_KIT}.')
    seed = entry['seed']
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError(f'Skin seed must be an integer in 0-{MAX_SEED}.')
    wear = entry['wear']
    if type(wear) not in (int, float) or not math.isfinite(wear) or not 0.0 <= wear <= 1.0:
        raise ValueError('Skin wear must be a finite number between 0.0 and 1.0.')
    stattrak = entry['stattrak']
    if type(stattrak) is not int or not -1 <= stattrak <= MAX_STATTRAK:
        raise ValueError(f'Skin stattrak must be -1 (off) or an integer in 0-{MAX_STATTRAK}.')
    custom_name = entry['custom_name']
    if not isinstance(custom_name, str) or len(custom_name) > MAX_CUSTOM_NAME or any(not 0x20 <= ord(ch) <= 0x7E for ch in custom_name):
        raise ValueError(f'Skin custom_name must be up to {MAX_CUSTOM_NAME} printable ASCII characters.')
    mesh_group = entry['mesh_group']
    if not isinstance(mesh_group, str) or mesh_group not in MESH_GROUPS:
        raise ValueError('Skin mesh_group must be auto, modern, or legacy.')
    return {
        'paint_kit': paint_kit,
        'seed': seed,
        'wear': round(float(wear), 6),
        'stattrak': stattrak,
        'custom_name': custom_name,
        'mesh_group': mesh_group,
    }


def validate_skins(skins):
    if not isinstance(skins, dict):
        raise ValueError('skins must be a mapping of weapon definition IDs to skin settings.')
    if len(skins) > MAX_SKINS:
        raise ValueError(f'At most {MAX_SKINS} weapon skins may be configured at once.')
    normalized = {}
    for key, entry in skins.items():
        if not isinstance(key, str) or not WEAPON_KEY_RE.fullmatch(key):
            raise ValueError('Skin weapon keys must be canonical weapon definition integers (1-65535).')
        weapon_id = int(key)
        if not 1 <= weapon_id <= 65535:
            raise ValueError('Skin weapon definition ID must be in 1-65535.')
        normalized[key] = validate_skin_entry(entry)
    return normalized


def loadout_path(directory):
    # Leading dot excludes the skin bridge file from named gameplay configs.
    return Path(directory) / '.skin-loadout.json'


def loadout_document(enabled, skins):
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean.')
    clean = validate_skins(skins)
    entries = []
    for key in sorted(clean, key=int):
        item = clean[key]
        entries.append({
            'weapon_definition': int(key),
            'paint_kit': item['paint_kit'],
            'seed': item['seed'],
            'wear': item['wear'],
            'stattrak': item['stattrak'],
            'custom_name': item['custom_name'],
            'mesh_group': MESH_GROUPS[item['mesh_group']],
        })
    return {'version': 1, 'enabled': enabled, 'entries': entries}


def export_loadout(directory, enabled, skins):
    path = loadout_path(directory)
    document = loadout_document(enabled, skins)
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
    return path
