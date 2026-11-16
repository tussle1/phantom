"""Tests for local skin catalog, validation, config migration, CLI export, and C++ bridge."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import phantom
from native.config import Config, load_config, save_config, validate_config
from native.gui_model import SettingsModel
from native.presets import PRESETS, preset_config
from native.skin_bridge import SkinFoundationBridge, probe_foundation
from native.skins import (
    DEFAULT_SKIN_ENTRY,
    MAX_SKINS,
    MESH_GROUPS,
    PAINT_KITS,
    RARITY_COLORS,
    STARTER_LOADOUTS,
    WEAPON_BY_ID,
    WEAPON_CATEGORIES,
    WEAPONS,
    export_loadout,
    kit_by_id,
    kits_for_weapon,
    loadout_document,
    loadout_path,
    validate_skin_entry,
    validate_skins,
    weapon_name,
    wear_tier,
)


class SkinCatalogTests(unittest.TestCase):
    def test_catalog_consistency(self):
        ids = [w.definition for w in WEAPONS]
        self.assertEqual(len(ids), len(set(ids)))
        for weapon in WEAPONS:
            self.assertTrue(1 <= weapon.definition <= 65535)
            self.assertIn(weapon.category, WEAPON_CATEGORIES)
            self.assertTrue(weapon.name)
            self.assertEqual(weapon_name(weapon.definition), weapon.name)
        self.assertEqual(weapon_name(507), 'Weapon #507')

        for kit in PAINT_KITS:
            self.assertIn(kit.rarity, RARITY_COLORS)
            self.assertIn(kit.mesh_group, MESH_GROUPS)
            self.assertEqual(len(kit.swatches), 3)
            for hex_color in kit.swatches:
                self.assertRegex(hex_color, r'^#[0-9a-fA-F]{6}$')
            for w_id in kit.weapons:
                self.assertIn(w_id, WEAPON_BY_ID)

        ak_kits = kits_for_weapon(7)
        self.assertEqual(ak_kits[0].paint_kit, 0)
        self.assertTrue(any(k.paint_kit == 282 and k.name == 'Redline' for k in ak_kits))
        self.assertEqual(kit_by_id(282, 7).name, 'Redline')
        self.assertIsNone(kit_by_id(999999, 7))

    def test_wear_tiers_and_starter_loadouts(self):
        self.assertEqual(wear_tier(0.0)[1], 'FN')
        self.assertEqual(wear_tier(0.069)[1], 'FN')
        self.assertEqual(wear_tier(0.07)[1], 'MW')
        self.assertEqual(wear_tier(0.15)[1], 'FT')
        self.assertEqual(wear_tier(0.38)[1], 'WW')
        self.assertEqual(wear_tier(0.45)[1], 'BS')
        self.assertEqual(wear_tier(1.0)[1], 'BS')
        for name, loadout in STARTER_LOADOUTS.items():
            with self.subTest(pack=name):
                validated = validate_skins(loadout)
                self.assertEqual(len(validated), len(loadout))


class SkinValidationAndConfigTests(unittest.TestCase):
    def test_valid_skin_roundtrip_and_isolation(self):
        entry = {
            'paint_kit': 282,
            'seed': 420,
            'wear': 0.15,
            'stattrak': 1337,
            'custom_name': 'phantom redline',
            'mesh_group': 'legacy',
        }
        raw_skins = {'7': dict(entry)}
        config = validate_config({'version': 1, 'settings': {**asdict(Config()), 'skin_changer': True, 'skins': raw_skins}})
        raw_skins['7']['paint_kit'] = 999
        self.assertEqual(config.skins['7']['paint_kit'], 282)
        self.assertTrue(config.skin_changer)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'skins-test.json'
            save_config(path, config)
            loaded = load_config(path)
            self.assertEqual(asdict(loaded), asdict(config))

    def test_reject_invalid_skin_entries_and_keys(self):
        base = dict(DEFAULT_SKIN_ENTRY)
        bad_entries = [
            {**base, 'paint_kit': -1},
            {**base, 'paint_kit': True},
            {**base, 'paint_kit': 0x80000000},
            {**base, 'seed': -1},
            {**base, 'seed': 1001},
            {**base, 'seed': 1.5},
            {**base, 'wear': -0.001},
            {**base, 'wear': 1.001},
            {**base, 'wear': float('nan')},
            {**base, 'wear': float('inf')},
            {**base, 'wear': True},
            {**base, 'stattrak': -2},
            {**base, 'stattrak': 1000000},
            {**base, 'stattrak': False},
            {**base, 'custom_name': 'x' * 33},
            {**base, 'custom_name': 'bad\nname'},
            {**base, 'custom_name': 'non-ascii-\u00e9'},
            {**base, 'mesh_group': 'invalid'},
            {**base, 'mesh_group': 1},
            {**base, 'extra': 1},
            {k: v for k, v in base.items() if k != 'mesh_group'},
        ]
        for bad in bad_entries:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_skin_entry(bad)

        for bad_key in ('0', '07', '-1', '65536', 'ak47', ' 7', 7):
            with self.subTest(bad_key=bad_key), self.assertRaises(ValueError):
                validate_skins({bad_key: dict(base)})

        too_many = {str(i): dict(base) for i in range(1, MAX_SKINS + 2)}
        with self.assertRaises(ValueError):
            validate_skins(too_many)

    def test_legacy_config_migration_and_preset_preservation(self):
        legacy = asdict(Config())
        legacy.pop('skin_changer')
        legacy.pop('skins')
        upgraded = validate_config({'version': 1, 'settings': legacy})
        self.assertFalse(upgraded.skin_changer)
        self.assertEqual(upgraded.skins, {})
        self.assertNotIn('skins', legacy)

        personal = Config(skin_changer=True, skins={'7': {**DEFAULT_SKIN_ENTRY, 'paint_kit': 707}})
        for name in PRESETS:
            applied = preset_config(name, personal)
            self.assertFalse(applied.skin_changer)
            self.assertEqual(applied.skins, personal.skins)


class SkinModelAndExportTests(unittest.TestCase):
    def test_model_operations_and_dotfile_export(self):
        with tempfile.TemporaryDirectory() as directory:
            model = SettingsModel(directory)
            model.set('skin_changer', True)
            model.set_skin(7, {**DEFAULT_SKIN_ENTRY, 'paint_kit': 282, 'seed': 12, 'wear': 0.15,
                               'stattrak': 100, 'custom_name': 'ak', 'mesh_group': 'legacy'})
            self.assertIn('7', model.config.skins)
            before = model.document()
            with self.assertRaises(ValueError):
                model.set_skin(7, {**DEFAULT_SKIN_ENTRY, 'wear': 5.0})
            self.assertEqual(model.document(), before)

            exported = model.export_skins()
            self.assertEqual(exported, loadout_path(directory))
            self.assertEqual(model.names(), [])
            doc = json.loads(exported.read_text(encoding='utf-8'))
            self.assertEqual(doc['version'], 1)
            self.assertTrue(doc['enabled'])
            self.assertEqual(len(doc['entries']), 1)
            self.assertEqual(doc['entries'][0]['weapon_definition'], 7)
            self.assertEqual(doc['entries'][0]['mesh_group'], 2)

            model.apply_skin_pack('phantom neon')
            self.assertEqual(len(model.config.skins), len(STARTER_LOADOUTS['phantom neon']))
            self.assertTrue(model.remove_skin(7))
            self.assertFalse(model.remove_skin(7))
            model.clear_skins()
            self.assertEqual(model.config.skins, {})

    def test_cli_export_skins(self):
        with tempfile.TemporaryDirectory() as directory:
            model = SettingsModel(directory)
            model.set('skin_changer', True)
            model.set_skin(9, {**DEFAULT_SKIN_ENTRY, 'paint_kit': 344, 'mesh_group': 'legacy'})
            model.save('skins')
            rc = phantom.main(['--config-dir', directory, '--config', 'skins', '--export-skins'])
            self.assertEqual(rc, 0)
            exported = loadout_path(directory)
            self.assertTrue(exported.is_file())
            doc = json.loads(exported.read_text(encoding='utf-8'))
            self.assertEqual(doc['entries'][0]['weapon_definition'], 9)
            self.assertEqual(doc['entries'][0]['paint_kit'], 344)

    def test_probe_foundation_missing_is_safe(self):
        result = probe_foundation()
        self.assertIn('summary', result)
        self.assertIsInstance(result['summary'], str)


class SkinCppBridgeIntegrationTests(unittest.TestCase):
    def test_python_to_cpp_shared_library_roundtrip(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which('g++')
        if sys.platform != 'linux' or not compiler:
            self.skipTest('Direct g++ shared-library bridge test runs on Linux with g++.')
        with tempfile.TemporaryDirectory() as directory:
            lib_path = Path(directory) / 'libphantom-internal-foundation.so'
            cmd = [
                compiler, '-std=c++17', '-O2', '-fPIC', '-shared',
                f'-I{root / "cpp/include"}',
                str(root / 'cpp/src/api.cpp'),
                str(root / 'cpp/src/core.cpp'),
                str(root / 'cpp/src/cosmetics.cpp'),
                str(root / 'cpp/src/runtime.cpp'),
                '-pthread', '-o', str(lib_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            bridge = SkinFoundationBridge(lib_path)
            status = bridge.status()
            self.assertEqual(status['abi_version'], 1)
            self.assertFalse(status['runtime_available'])
            self.assertFalse(status['game_adapter_ready'])

            skins = STARTER_LOADOUTS['phantom neon']
            exported = export_loadout(directory, True, skins)
            loaded = bridge.load_skin_file(exported)
            self.assertEqual(len(loaded), len(skins))
            by_weapon = {item['weapon_definition']: item for item in loaded}
            self.assertEqual(by_weapon[7]['paint_kit'], 707)
            self.assertEqual(by_weapon[7]['stattrak'], 1337)
            self.assertEqual(by_weapon[7]['custom_name'], 'phantom')
            self.assertEqual(by_weapon[7]['mesh_group'], 2)

            # Direct sync_skins roundtrip matches as well.
            synced = bridge.sync_skins({'9': {**DEFAULT_SKIN_ENTRY, 'paint_kit': 344, 'seed': 55,
                                              'wear': 0.01, 'stattrak': -1, 'custom_name': 'dlore', 'mesh_group': 'legacy'}})
            self.assertEqual(synced, 1)
            listed = bridge.list_preferences()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]['weapon_definition'], 9)
            self.assertEqual(listed[0]['paint_kit'], 344)
            self.assertEqual(listed[0]['custom_name'], 'dlore')
            self.assertEqual(listed[0]['mesh_group'], 2)

            # Verify probe_foundation discovers the built library in extra_dirs.
            probed = probe_foundation((directory,))
            self.assertTrue(probed['found'])
            self.assertIn('ABI v1', probed['summary'])


if __name__ == '__main__':
    unittest.main()
