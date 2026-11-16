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
    model_path: str = ''
    is_knife: bool = False


@dataclass(frozen=True)
class PaintKit:
    paint_kit: int
    name: str
    rarity: str
    swatches: tuple[str, str, str]
    weapons: tuple[int, ...]
    mesh_group: str = 'auto'


WEAPON_CATEGORIES = ('All', 'Knives', 'Rifles', 'Snipers', 'Pistols', 'SMGs', 'Heavy')

DEFAULT_KNIFE_DEFINITIONS = frozenset((42, 59))
DEFAULT_KNIFE_MODELS = {
    42: 'weapons/models/knife/knife_default_ct/weapon_knife_default_ct.vmdl',
    59: 'weapons/models/knife/knife_default_t/weapon_knife_default_t.vmdl',
}

KNIVES = (
    WeaponDef(500, 'Bayonet', 'Knives', 'weapons/models/knife/knife_bayonet/weapon_knife_bayonet.vmdl', True),
    WeaponDef(503, 'Classic Knife', 'Knives', 'weapons/models/knife/knife_css/weapon_knife_css.vmdl', True),
    WeaponDef(505, 'Flip Knife', 'Knives', 'weapons/models/knife/knife_flip/weapon_knife_flip.vmdl', True),
    WeaponDef(506, 'Gut Knife', 'Knives', 'weapons/models/knife/knife_gut/weapon_knife_gut.vmdl', True),
    WeaponDef(507, 'Karambit', 'Knives', 'weapons/models/knife/knife_karambit/weapon_knife_karambit.vmdl', True),
    WeaponDef(508, 'M9 Bayonet', 'Knives', 'weapons/models/knife/knife_m9/weapon_knife_m9.vmdl', True),
    WeaponDef(509, 'Huntsman Knife', 'Knives', 'weapons/models/knife/knife_tactical/weapon_knife_tactical.vmdl', True),
    WeaponDef(512, 'Falchion Knife', 'Knives', 'weapons/models/knife/knife_falchion/weapon_knife_falchion.vmdl', True),
    WeaponDef(514, 'Bowie Knife', 'Knives', 'weapons/models/knife/knife_bowie/weapon_knife_bowie.vmdl', True),
    WeaponDef(515, 'Butterfly Knife', 'Knives', 'weapons/models/knife/knife_butterfly/weapon_knife_butterfly.vmdl', True),
    WeaponDef(516, 'Shadow Daggers', 'Knives', 'weapons/models/knife/knife_push/weapon_knife_push.vmdl', True),
    WeaponDef(517, 'Paracord Knife', 'Knives', 'weapons/models/knife/knife_cord/weapon_knife_cord.vmdl', True),
    WeaponDef(518, 'Survival Knife', 'Knives', 'weapons/models/knife/knife_canis/weapon_knife_canis.vmdl', True),
    WeaponDef(519, 'Ursus Knife', 'Knives', 'weapons/models/knife/knife_ursus/weapon_knife_ursus.vmdl', True),
    WeaponDef(520, 'Navaja Knife', 'Knives', 'weapons/models/knife/knife_gypsy_jackknife/weapon_knife_gypsy_jackknife.vmdl', True),
    WeaponDef(521, 'Nomad Knife', 'Knives', 'weapons/models/knife/knife_outdoor/weapon_knife_outdoor.vmdl', True),
    WeaponDef(522, 'Stiletto Knife', 'Knives', 'weapons/models/knife/knife_stiletto/weapon_knife_stiletto.vmdl', True),
    WeaponDef(523, 'Talon Knife', 'Knives', 'weapons/models/knife/knife_widowmaker/weapon_knife_widowmaker.vmdl', True),
    WeaponDef(525, 'Skeleton Knife', 'Knives', 'weapons/models/knife/knife_skeleton/weapon_knife_skeleton.vmdl', True),
    WeaponDef(526, 'Kukri Knife', 'Knives', 'weapons/models/knife/knife_kukri/weapon_knife_kukri.vmdl', True),
)
KNIFE_IDS = tuple(k.definition for k in KNIVES)
KNIFE_DEFINITIONS = frozenset(KNIFE_IDS)

WEAPONS = (
    *KNIVES,
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
    # Knives — universal finishes available locally on all 20 custom CS2 knives
    PaintKit(38, 'Fade', 'Covert', ('#ff6fa8', '#f5b841', '#8858ff'), KNIFE_IDS, 'modern'),
    PaintKit(413, 'Marble Fade', 'Covert', ('#e84040', '#f0cf4b', '#3076e8'), KNIFE_IDS, 'modern'),
    PaintKit(409, 'Tiger Tooth', 'Covert', ('#f0b636', '#a86b18', '#332210'), KNIFE_IDS, 'modern'),
    PaintKit(415, 'Doppler (Ruby)', 'Covert', ('#e81c45', '#960e2e', '#380914'), KNIFE_IDS, 'modern'),
    PaintKit(416, 'Doppler (Sapphire)', 'Covert', ('#2462ff', '#132fa6', '#0c164a'), KNIFE_IDS, 'modern'),
    PaintKit(417, 'Doppler (Black Pearl)', 'Covert', ('#4f2e78', '#221438', '#0d0914'), KNIFE_IDS, 'modern'),
    PaintKit(418, 'Doppler (Phase 1)', 'Covert', ('#b02c6c', '#3c1b3a', '#161020'), KNIFE_IDS, 'modern'),
    PaintKit(419, 'Doppler (Phase 2)', 'Covert', ('#f252a6', '#7e2260', '#2b1026'), KNIFE_IDS, 'modern'),
    PaintKit(420, 'Doppler (Phase 3)', 'Covert', ('#2e8c78', '#244b7a', '#101824'), KNIFE_IDS, 'modern'),
    PaintKit(421, 'Doppler (Phase 4)', 'Covert', ('#3278f0', '#1d3670', '#0e1628'), KNIFE_IDS, 'modern'),
    PaintKit(568, 'Gamma Doppler (Emerald)', 'Covert', ('#2ce878', '#118f48', '#0a331d'), KNIFE_IDS, 'modern'),
    PaintKit(569, 'Gamma Doppler (Phase 1)', 'Covert', ('#2ea874', '#1b4a42', '#101d20'), KNIFE_IDS, 'modern'),
    PaintKit(570, 'Gamma Doppler (Phase 2)', 'Covert', ('#3ce08c', '#1c7e54', '#0e2c22'), KNIFE_IDS, 'modern'),
    PaintKit(571, 'Gamma Doppler (Phase 3)', 'Covert', ('#32d2c8', '#1a6875', '#0f222a'), KNIFE_IDS, 'modern'),
    PaintKit(572, 'Gamma Doppler (Phase 4)', 'Covert', ('#68e048', '#248c5e', '#102820'), KNIFE_IDS, 'modern'),
    # Knives — authentic per-knife Gamma & Dreams/Riptide IDs (with canonical fallback for newer knives)
    PaintKit(558, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (500,), 'modern'),
    PaintKit(559, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (505,), 'modern'),
    PaintKit(560, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (506,), 'modern'),
    PaintKit(561, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (507, 503, 517, 518, 519, 520, 521, 522, 523, 525, 526), 'modern'),
    PaintKit(562, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (508,), 'modern'),
    PaintKit(1104, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (514,), 'modern'),
    PaintKit(1105, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (515,), 'modern'),
    PaintKit(1106, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (512,), 'modern'),
    PaintKit(1107, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (509,), 'modern'),
    PaintKit(1108, 'Lore', 'Covert', ('#e6bd4e', '#9a7424', '#2c2920'), (516,), 'modern'),
    PaintKit(573, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (500,), 'modern'),
    PaintKit(574, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (505,), 'modern'),
    PaintKit(575, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (506,), 'modern'),
    PaintKit(576, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (507, 503, 517, 518, 519, 520, 521, 522, 523, 525, 526), 'modern'),
    PaintKit(577, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (508,), 'modern'),
    PaintKit(1114, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (514,), 'modern'),
    PaintKit(1115, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (515,), 'modern'),
    PaintKit(1116, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (512,), 'modern'),
    PaintKit(1117, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (509,), 'modern'),
    PaintKit(1118, 'Autotronic', 'Covert', ('#cc2936', '#c4cad4', '#2a2d36'), (516,), 'modern'),
    PaintKit(563, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (500,), 'modern'),
    PaintKit(564, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (505,), 'modern'),
    PaintKit(565, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (506,), 'modern'),
    PaintKit(566, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (507, 503, 517, 518, 519, 520, 521, 522, 523, 525, 526), 'modern'),
    PaintKit(567, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (508,), 'modern'),
    PaintKit(1109, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (514,), 'modern'),
    PaintKit(1110, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (515,), 'modern'),
    PaintKit(1111, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (512,), 'modern'),
    PaintKit(1112, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (509,), 'modern'),
    PaintKit(1113, 'Black Laminate', 'Covert', ('#3a3e46', '#22242a', '#6b5344'), (516,), 'modern'),
    PaintKit(580, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (500, 505, 506), 'modern'),
    PaintKit(581, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (508, 503, 517, 518, 519, 520, 521, 522, 523, 525, 526), 'modern'),
    PaintKit(582, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (507,), 'modern'),
    PaintKit(1119, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (514,), 'modern'),
    PaintKit(1120, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (515,), 'modern'),
    PaintKit(1121, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (512,), 'modern'),
    PaintKit(1122, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (509,), 'modern'),
    PaintKit(1123, 'Freehand', 'Covert', ('#8452c8', '#e6e8f0', '#2b1e48'), (516,), 'modern'),
    PaintKit(578, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (500, 505, 506, 507, 503, 517, 518, 519, 520, 521, 522, 523, 525, 526), 'modern'),
    PaintKit(579, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (508,), 'modern'),
    PaintKit(1124, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (514,), 'modern'),
    PaintKit(1125, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (515,), 'modern'),
    PaintKit(1126, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (512,), 'modern'),
    PaintKit(1127, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (509,), 'modern'),
    PaintKit(1128, 'Bright Water', 'Covert', ('#3874c4', '#72a8e6', '#1e3554'), (516,), 'modern'),
    # Knives — classic & tactical finishes across all 20 custom CS2 knives
    PaintKit(12, 'Crimson Web', 'Covert', ('#b51d2a', '#5c1118', '#1a1a1f'), KNIFE_IDS, 'modern'),
    PaintKit(59, 'Slaughter', 'Covert', ('#d42e48', '#8a182c', '#3c1420'), KNIFE_IDS, 'modern'),
    PaintKit(44, 'Case Hardened', 'Covert', ('#3e84e6', '#e0b84c', '#7a528c'), KNIFE_IDS, 'modern'),
    PaintKit(98, 'Ultraviolet', 'Covert', ('#6834b8', '#2a2234', '#16141a'), KNIFE_IDS, 'modern'),
    PaintKit(40, 'Night', 'Covert', ('#2c3342', '#1d222c', '#12151c'), KNIFE_IDS, 'modern'),
    PaintKit(735, 'Night Stripe', 'Covert', ('#3b4252', '#262b36', '#161920'), KNIFE_IDS, 'modern'),
    PaintKit(410, 'Damascus Steel', 'Covert', ('#cfd6df', '#8a94a3', '#49505c'), KNIFE_IDS, 'modern'),
    PaintKit(414, 'Rust Coat', 'Covert', ('#9c522c', '#6e3a20', '#3d2a20'), KNIFE_IDS, 'modern'),
    PaintKit(43, 'Stained', 'Covert', ('#c2c8d0', '#8f96a0', '#585e68'), KNIFE_IDS, 'modern'),
    PaintKit(42, 'Blue Steel', 'Covert', ('#607a9c', '#45546c', '#2c3442'), KNIFE_IDS, 'modern'),
    PaintKit(175, 'Scorched', 'Covert', ('#686258', '#3e3a34', '#22201d'), KNIFE_IDS, 'modern'),
    PaintKit(77, 'Boreal Forest', 'Covert', ('#4f6448', '#354230', '#20261e'), KNIFE_IDS, 'modern'),
    PaintKit(5, 'Forest DDPAT', 'Covert', ('#586c48', '#3d4c32', '#262d20'), KNIFE_IDS, 'modern'),
    PaintKit(72, 'Safari Mesh', 'Covert', ('#948a72', '#696250', '#3d3930'), KNIFE_IDS, 'modern'),
    PaintKit(143, 'Urban Masked', 'Covert', ('#a8acb4', '#6d717a', '#353840'), KNIFE_IDS, 'modern'),
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
    'knife gems': {
        '507': {'paint_kit': 415, 'seed': 387, 'wear': 0.006, 'stattrak': 777, 'custom_name': 'ruby', 'mesh_group': 'modern'},
        '515': {'paint_kit': 568, 'seed': 120, 'wear': 0.007, 'stattrak': 500, 'custom_name': 'emerald', 'mesh_group': 'modern'},
        '508': {'paint_kit': 416, 'seed': 42, 'wear': 0.008, 'stattrak': 333, 'custom_name': 'sapphire', 'mesh_group': 'modern'},
        '525': {'paint_kit': 44, 'seed': 403, 'wear': 0.015, 'stattrak': -1, 'custom_name': 'blue gem', 'mesh_group': 'modern'},
        '526': {'paint_kit': 38, 'seed': 763, 'wear': 0.004, 'stattrak': -1, 'custom_name': 'full fade', 'mesh_group': 'modern'},
    },
}


def is_custom_knife(definition):
    return int(definition) in KNIFE_DEFINITIONS


def is_knife(definition):
    value = int(definition)
    return value in KNIFE_DEFINITIONS or value in DEFAULT_KNIFE_DEFINITIONS


def knife_model_path(definition):
    value = int(definition)
    if value in DEFAULT_KNIFE_MODELS:
        return DEFAULT_KNIFE_MODELS[value]
    weapon = WEAPON_BY_ID.get(value)
    return weapon.model_path if weapon and weapon.is_knife else ''


def utl_string_token(text):
    """Compute Source 2 CUtlStringToken (MurmurHash2, seed 0x31415926)."""
    data = str(text).encode('utf-8')
    length = len(data)
    m = 0x5BD1E995
    h = (0x31415926 ^ length) & 0xFFFFFFFF
    idx = 0
    while idx + 4 <= length:
        k = int.from_bytes(data[idx:idx + 4], 'little')
        k = (k * m) & 0xFFFFFFFF
        k ^= (k >> 24)
        k = (k * m) & 0xFFFFFFFF
        h = (h * m) & 0xFFFFFFFF
        h ^= k
        idx += 4
    rem = length - idx
    if rem == 3:
        h ^= data[idx + 2] << 16
    if rem >= 2:
        h ^= data[idx + 1] << 8
    if rem >= 1:
        h ^= data[idx]
        h = (h * m) & 0xFFFFFFFF
    h ^= (h >> 13)
    h = (h * m) & 0xFFFFFFFF
    h ^= (h >> 15)
    return h & 0xFFFFFFFF


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


def display_weapon_name(definition):
    value = int(definition)
    base = weapon_name(value)
    return f'★ {base}' if is_custom_knife(value) else base


def validate_knife_override(value):
    if type(value) is not int:
        raise ValueError('knife_override must be 0 (off) or a custom CS2 knife definition ID.')
    if value != 0 and value not in KNIFE_DEFINITIONS:
        raise ValueError('knife_override must be 0 (off) or one of the 20 custom CS2 knives (500-526).')
    return value


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


def loadout_document(enabled, skins, knife_override=0):
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean.')
    clean = validate_skins(skins)
    clean_knife = validate_knife_override(knife_override)
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
    return {'version': 1, 'enabled': enabled, 'knife_override': clean_knife, 'entries': entries}


def export_loadout(directory, enabled, skins, knife_override=0):
    path = loadout_path(directory)
    document = loadout_document(enabled, skins, knife_override=knife_override)
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
