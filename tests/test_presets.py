from dataclasses import asdict
import tempfile
import unittest

from native.config import Config, validate_config
from native.gui_model import SettingsModel
from native.presets import PRESETS, PRESERVE, preset_config, preset_document, preset_filename


class PresetTests(unittest.TestCase):
    def test_all_presets_are_complete_valid_and_independent(self):
        for name in PRESETS:
            document = preset_document(name)
            self.assertEqual(asdict(validate_config(document)), document['settings'])
            document['settings']['keys']['menu_toggle'] = 1
            self.assertEqual(preset_config(name).keys['menu_toggle'], 0xA1)
            self.assertTrue(preset_filename(name).endswith('.json'))
        self.assertEqual(preset_config('defaults'), Config())

    def test_expected_features_are_explicit(self):
        for name in ('defaults', 'esp minimal', 'esp detailed'):
            config = preset_config(name)
            self.assertEqual(config.aim, 'off')
            self.assertFalse(config.trigger)
            self.assertFalse(config.bunny_hop)
        self.assertFalse(preset_config('esp minimal').skeleton)
        self.assertEqual(preset_config('esp minimal').max_distance_m, 100)
        self.assertTrue(preset_config('esp detailed').skeleton)
        aim = preset_config('smooth aim practice')
        self.assertEqual((aim.aim, aim.aim_fov, aim.smooth_time, aim.priority_bone), ('smooth',2,.2,'chest'))
        self.assertFalse(aim.esp)
        self.assertTrue(preset_config('combined practice').esp)
        self.assertTrue(preset_config('trigger practice').trigger)

    def test_model_preserves_keys_calibration_name_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            model = SettingsModel(directory)
            model.set_key('menu_toggle', 0x2D)
            model.set('mouse_yaw', .03)
            model.set('mouse_pitch', .04)
            bones = dict(model.config.bones);bones['head'] = 7;model.set('bones',bones)
            model.save('personal')
            before = model.path.read_bytes()
            original = asdict(model.config)
            revision = model.revision
            for name in PRESETS:
                model.apply_preset(name)
                for key in PRESERVE:
                    self.assertEqual(asdict(model.config)[key], original[key])
                self.assertEqual(model.name, 'personal')
                self.assertEqual(model.path.read_bytes(), before)
                self.assertEqual(model.names(), ['personal'])
            self.assertEqual(model.revision, revision+len(PRESETS))
            snapshot = model.document()
            with self.assertRaises(ValueError):
                model.apply_preset('missing')
            self.assertEqual(model.document(), snapshot)
            self.assertEqual(model.revision, revision+len(PRESETS))


if __name__ == '__main__':
    unittest.main()
