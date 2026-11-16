from dataclasses import asdict
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from native import appearance as ui
from native.gui_model import SettingsModel


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_defaults_and_round_trip_are_separate_from_gameplay(self):
        preferences, warning = ui.load(self.directory)
        self.assertEqual(preferences, ui.Appearance())
        self.assertFalse(warning)
        preferences.accent = '#69b8ff'
        preferences.scale = 125
        preferences.start_expanded = False
        ui.save(self.directory, preferences)
        self.assertEqual(ui.load(self.directory), (preferences, ''))
        model = SettingsModel(self.directory)
        self.assertEqual(model.names(), [])
        self.assertNotIn('appearance', model.document()['settings'])
        model.save('practice')
        self.assertEqual(model.names(), ['practice'])
        self.assertEqual(ui.load(self.directory)[0], preferences)

    def test_invalid_values_rejected_before_replacing_saved_file(self):
        ui.save(self.directory, ui.Appearance())
        original = ui.preferences_path(self.directory).read_bytes()
        for key,value in [('accent','red'),('background','#abc'),('scale',True),
                          ('scale',1000),('spacing','huge'),('start_expanded',1)]:
            preferences = ui.Appearance(**{**asdict(ui.Appearance()), key:value})
            with self.assertRaises(ValueError):
                ui.save(self.directory, preferences)
            self.assertEqual(ui.preferences_path(self.directory).read_bytes(), original)

    def test_corrupt_unknown_and_oversized_files_fall_back_without_overwrite(self):
        for content in ('not json', '{"version":1,"appearance":{}}', 'x'*8193):
            path = ui.preferences_path(self.directory)
            path.write_text(content)
            preferences, warning = ui.load(self.directory)
            self.assertEqual(preferences, ui.Appearance())
            self.assertTrue(warning)
            self.assertEqual(path.read_text(), content)

    def test_scale_applied_before_qt_and_external_override_preserved(self):
        ui.save(self.directory, ui.Appearance(scale=125))
        with patch.dict(os.environ, {}, clear=True):
            ui.configure_scale(self.directory)
            self.assertEqual(os.environ['QT_SCALE_FACTOR'], '1.25')
        with patch.dict(os.environ, {'QT_SCALE_FACTOR':'1.5'}, clear=True):
            ui.configure_scale(self.directory)
            self.assertEqual(os.environ['QT_SCALE_FACTOR'], '1.5')

    def test_palettes_support_dark_light_backgrounds_and_presets(self):
        for accent,background in ui.PRESETS.values():
            palette = ui.palette(ui.Appearance(accent=accent, background=background))
            self.assertEqual(palette['background'], background)
            self.assertEqual(palette['accent'], accent)
        self.assertNotEqual(ui.palette(ui.Appearance(background='#ffffff'))['ink'],
                            ui.palette(ui.Appearance(background='#000000'))['ink'])
        self.assertEqual(ui.mix('#000000','#ffffff',1),'#ffffff')


if __name__ == '__main__':
    unittest.main()
