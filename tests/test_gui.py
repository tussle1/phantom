"""Qt tests run offscreen when GUI dependencies/system libraries are available."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from native.gui import ControlPanel
    QT_AVAILABLE = True
except (ImportError, OSError):
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, 'Qt or required system libraries are not installed')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        profile = Path(__file__).resolve().parents[1]/'native/profiles/reference-26598758.json'
        self.panel = ControlPanel(profile, self.temp.name)
        self.panel.show()
        self.app.processEvents()

    def tearDown(self):
        self.panel.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_defaults_and_top_controls(self):
        self.assertFalse(self.panel.toggles['aim'].isChecked())
        self.assertFalse(self.panel.toggles['trigger'].isChecked())
        self.panel.sliders['aim_fov'].value.setValue(6)
        self.assertEqual(self.panel.model.config.aim_fov, 6)
        QTest.mouseClick(self.panel.toggles['esp'], Qt.MouseButton.LeftButton)
        self.assertFalse(self.panel.model.config.esp)
        self.panel.reset_setting('aim_fov')
        self.assertEqual(self.panel.sliders['aim_fov'].value.value(), 3)

    def test_tabs_expand_and_collapse(self):
        QTest.mouseClick(self.panel.more, Qt.MouseButton.LeftButton)
        self.assertFalse(self.panel.expanded)
        self.assertTrue(self.panel.details_scroll.isHidden())
        for name in ('Visuals', 'Input', 'Configs', 'Aim'):
            QTest.mouseClick(self.panel.tab_buttons[name], Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertTrue(self.panel.expanded)
            self.assertEqual(self.panel.page, name)
            self.assertFalse(self.panel.details_scroll.isHidden())

    def test_visual_controls(self):
        self.panel.select_page('Visuals')
        QTest.mouseClick(self.panel.toggles['skeleton'], Qt.MouseButton.LeftButton)
        self.assertFalse(self.panel.model.config.skeleton)
        self.panel.sliders['max_distance_m'].value.setValue(240)
        self.assertEqual(self.panel.model.config.max_distance_m, 240)

    def test_binding_capture_and_escape(self):
        self.panel.select_page('Input')
        button = self.panel.binding_buttons['aim_hold']
        self.panel.begin_capture('aim_hold', button)
        QTest.keyClick(button, Qt.Key.Key_F4)
        self.assertEqual(self.panel.model.config.keys['aim_hold'], 0x73)
        self.assertEqual(button.text(), 'F4')
        self.panel.begin_capture('aim_hold', button)
        QTest.keyClick(button, Qt.Key.Key_Escape)
        self.assertIsNone(self.panel.capture)
        self.panel.select_page('Aim')
        self.app.processEvents()
        self.panel.refresh()  # No stale references to deleted binding buttons.

    def test_save_named_config(self):
        self.panel.select_page('Configs')
        self.panel.name_edit.setText('test profile')
        self.panel.save_named()
        self.assertIn('test profile', self.panel.model.names())
        self.assertEqual(self.panel.model.name, 'test profile')

    def test_start_failure_is_visible(self):
        with patch.object(self.panel.session, 'start', side_effect=OSError('test start rejected')):
            self.panel.start_runtime()
        self.assertIn('test start rejected', self.panel.message.text())
        self.assertTrue(self.panel.start_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
