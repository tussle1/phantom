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
    from PySide6.QtGui import QFont, QFontInfo, QFontMetrics
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
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

    def test_poppins_is_loaded_and_ui_text_has_real_glyphs(self):
        from native.typography import configure_fonts, ui_font, REQUIRED_TEXT
        self.assertEqual(configure_fonts(), 'Poppins')
        self.assertEqual(self.panel.font().family(), 'Poppins')
        font = ui_font(10)
        self.assertIn(QFontInfo(font).family(), ('Poppins', 'Poppins Regular'))
        metrics = QFontMetrics(font)
        self.assertTrue(all(metrics.inFontUcs4(ord(c)) for c in REQUIRED_TEXT))
        self.assertGreater(metrics.horizontalAdvance('Phantom - Start runtime'), 0)

    def test_selected_logo_and_window_icon_are_loaded(self):
        self.assertFalse(self.panel.logo_label.pixmap().isNull())
        self.assertEqual(self.panel.logo_label.size().width(), 28)
        self.assertEqual(self.panel.logo_label.pixmap().devicePixelRatio(), 2)
        self.assertFalse(self.panel.windowIcon().isNull())
        self.assertFalse(self.app.windowIcon().isNull())
        self.assertFalse(self.panel.windowIcon().pixmap(16,16).isNull())
        self.assertFalse(self.panel.windowIcon().pixmap(256,256).isNull())

    def test_appearance_preview_save_reopen_and_reset(self):
        from native import appearance
        original = self.panel.model.document()
        QTest.mouseClick(self.panel.appearance_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.panel.page, 'Appearance')
        self.panel.theme_combo.setCurrentText('midnight')
        self.assertEqual(self.panel.appearance_palette['accent'], '#69b8ff')
        self.assertIn('#141e30', self.panel.styleSheet())
        self.panel.appearance_controls['spacing'].setCurrentText('compact')
        self.assertEqual(self.panel.hero.height(), 88)
        self.panel.appearance_controls['scale'].setCurrentText('125%')
        self.panel.appearance_controls['start_expanded'].setCurrentText('compact')
        self.panel.save_appearance()
        saved, warning = appearance.load(self.temp.name)
        self.assertFalse(warning)
        self.assertEqual(saved.scale, 125)
        self.assertFalse(saved.start_expanded)
        reopened = ControlPanel(self.panel.profile_path, self.temp.name)
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.expanded)
        self.assertEqual(reopened.appearance.background, '#141e30')
        self.assertEqual(self.panel.model.document(), original)
        self.panel.reset_appearance()
        self.assertEqual(self.panel.appearance, appearance.Appearance())
        self.assertEqual(self.panel.hero.height(), 104)
        self.assertEqual(appearance.load(self.temp.name)[0], saved)  # Reset is preview until saved.

    def test_custom_color_cancel_and_accept(self):
        from PySide6.QtGui import QColor
        self.panel.select_page('Appearance')
        before = self.panel.appearance.accent
        with patch('native.gui.QColorDialog.getColor', return_value=QColor()):
            self.panel.choose_color('accent')
        self.assertEqual(self.panel.appearance.accent, before)
        with patch('native.gui.QColorDialog.getColor', return_value=QColor('#21aabb')):
            self.panel.choose_color('accent')
        self.assertEqual(self.panel.appearance.accent, '#21aabb')
        self.assertEqual(self.panel.theme_combo.currentText(), 'custom')
        self.panel.select_page('Input')
        self.assertEqual(self.panel.appearance_palette['accent'], '#21aabb')

    def test_presets_confirm_cancel_and_preserve_bindings(self):
        from PySide6.QtWidgets import QMessageBox
        self.panel.model.set_key('menu_toggle', 0x2D)
        self.panel.select_page('Configs')
        self.panel.preset_combo.setCurrentText('combined practice')
        before = self.panel.model.document()
        with patch('native.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            QTest.mouseClick(self.panel.preset_apply_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.panel.model.document(), before)
        appearance = self.panel.appearance
        with patch('native.gui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as question:
            QTest.mouseClick(self.panel.preset_apply_button, Qt.MouseButton.LeftButton)
            self.assertEqual(question.call_args.args[-1], QMessageBox.StandardButton.No)
        self.assertEqual(self.panel.model.config.aim, 'smooth')
        self.assertTrue(self.panel.model.config.esp)
        self.assertEqual(self.panel.model.config.keys['menu_toggle'], 0x2D)
        self.assertEqual(self.panel.model.names(), [])
        self.assertEqual(self.panel.name_edit.text(), 'combined-practice')
        self.assertIs(self.panel.appearance, appearance)
        self.panel.select_page('Aim')
        self.assertEqual(self.panel.combos['priority_bone'].currentText(), 'chest')

    def test_preset_is_blocked_while_worker_exists(self):
        self.panel.select_page('Configs')
        before = self.panel.model.document()
        self.panel.session.process = object()
        try:
            with patch('native.gui.QMessageBox.question') as question:
                self.panel.apply_selected_preset()
                question.assert_not_called()
            self.assertEqual(self.panel.model.document(), before)
            self.assertIn('Stop the runtime', self.panel.message.text())
        finally:
            self.panel.session.process = None

    def test_skeleton_editor_targets_style_and_persistence(self):
        from PySide6.QtCore import QPoint
        self.panel.select_page('Visuals')
        QTest.mouseClick(self.panel.editor_button, Qt.MouseButton.LeftButton)
        editor = self.panel.esp_editor
        self.app.processEvents()
        self.assertTrue(editor.isVisible())
        self.assertTrue(editor.isModal())
        original_aim = self.panel.model.config.aim
        for target in ('head','neck','chest','pelvis'):
            x,y = editor.preview.points()[target]
            QTest.mouseClick(editor.preview,Qt.MouseButton.LeftButton,pos=QPoint(round(x),round(y)))
            self.assertEqual(self.panel.model.config.priority_bone,target)
        self.assertEqual(self.panel.model.config.aim,original_aim)
        QTest.keyClick(editor.preview,Qt.Key.Key_1)
        self.assertEqual(self.panel.model.config.priority_bone,'head')
        checkbox = editor.style_checks['box']
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton,pos=QPoint(8,checkbox.height()//2))
        editor.width_combo.setCurrentText('3')
        editor.change_style('visible_color','#21aabb')
        self.assertTrue(self.panel.model.config.esp_style['box'])
        editor.save_config()
        from native.gui_model import SettingsModel
        restored = SettingsModel(self.temp.name).config
        self.assertEqual(restored.esp_style['visible_color'],'#21aabb')
        self.assertEqual(restored.esp_style['line_width'],3)
        before = self.panel.model.document()
        editor.change_style('visible_color','#000000')
        self.assertEqual(self.panel.model.document(),before)
        editor.close()
        self.panel.select_page('Aim')
        self.assertEqual(self.panel.combos['priority_bone'].currentText(),'head')

    def test_version_is_displayed(self):
        self.assertTrue(any(label.text() == 'phantom v1.2.0' for label in self.panel.findChildren(QLabel)))

    def wait_for_motion(self, motion):
        # Wait for completion, not an assumed number of delivered Windows timer
        # ticks. Loaded runners can still be one frame short after duration+50ms.
        for _ in range(100):
            if motion.state() == motion.State.Stopped:
                return
            QTest.qWait(20)
        self.fail('GUI animation did not finish within two seconds')

    def test_toggle_animation_reverses_and_follows_blocked_model_refresh(self):
        from native.gui import Toggle
        toggle = Toggle(False)
        self.addCleanup(toggle.deleteLater)
        toggle.setChecked(True)
        toggle.motion.setCurrentTime(70)
        self.assertGreater(toggle.position, 0)
        self.assertLess(toggle.position, 1)
        toggle.setChecked(False)
        self.wait_for_motion(toggle.motion)
        self.assertAlmostEqual(toggle.position, 0)
        toggle.blockSignals(True)
        toggle.setChecked(True)
        self.wait_for_motion(toggle.motion)
        self.assertAlmostEqual(toggle.position, 1)
        self.assertTrue(toggle.isChecked())

    def test_hover_and_page_fades_settle_after_rapid_changes(self):
        button = self.panel.start_button
        button.animate_hover(1.0)
        button.hover_motion.setCurrentTime(60)
        self.assertGreater(button.hover_progress, 0)
        button.animate_hover(0.0)
        self.wait_for_motion(button.hover_motion)
        self.assertAlmostEqual(button.hover_progress, 0)
        for name in ('Input', 'Configs', 'Aim', 'Visuals'):
            self.panel.select_page(name)
        self.wait_for_motion(self.panel.page_motion)
        self.assertAlmostEqual(self.panel.details_opacity.opacity(), 1)
        self.assertEqual(self.panel.page, 'Visuals')
        self.panel.toggle_more()
        self.assertAlmostEqual(self.panel.details_opacity.opacity(), 1)
        self.panel.toggle_more()
        self.wait_for_motion(self.panel.page_motion)
        self.assertAlmostEqual(self.panel.details_opacity.opacity(), 1)

    def test_horizontal_layout_and_compact_restore(self):
        self.assertGreater(self.panel.width(), self.panel.height())
        self.assertGreaterEqual(self.panel.details_scroll.x(), self.panel.overview.width())
        self.assertGreater(self.panel.details_scroll.width(), 300)
        for page in ('Visuals', 'Aim', 'Input', 'Configs', 'Appearance'):
            self.panel.select_page(page)
            self.app.processEvents()
            self.assertGreater(self.panel.width(), self.panel.height())
            self.assertTrue(self.panel.details_scroll.isVisible())
        self.panel.toggle_more();self.app.processEvents()
        self.assertEqual(self.panel.width(), 440)
        self.assertFalse(self.panel.details_scroll.isVisible())
        self.panel.toggle_more();self.app.processEvents()
        self.assertGreater(self.panel.width(), self.panel.height())

    def test_lowercase_is_presentation_only(self):
        from native.typography import ui_font
        self.assertEqual(ui_font(10).capitalization(), QFont.Capitalization.AllLowercase)
        for page in ('Visuals', 'Aim', 'Input', 'Configs', 'Appearance'):
            self.panel.select_page(page)
            self.app.processEvents()
            for widget in self.panel.findChildren(QLabel) + self.panel.findChildren(QPushButton):
                self.assertEqual(widget.font().capitalization(), QFont.Capitalization.AllLowercase)
        self.panel.model.save('MixedCase')
        self.assertEqual(self.panel.model.name, 'MixedCase')
        self.assertTrue((Path(self.temp.name)/'MixedCase.json').is_file())

    def test_menu_toggle_hides_reopens_and_controls_pause_state(self):
        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.session.menu_visible)
        self.panel.toggle_menu()
        self.assertFalse(self.panel.isVisible())
        self.assertFalse(self.panel.session.menu_visible)
        self.assertTrue(self.panel.menu_timer.isActive())
        self.panel.toggle_menu()
        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.session.menu_visible)

    def test_menu_hotkey_polls_even_without_a_runtime(self):
        pressed = set()
        self.panel.menu_hotkey.read_key = lambda vk: vk in pressed
        self.panel.menu_hotkey.prime(0xA1)
        pressed.add(0xA1);self.panel.poll_menu_hotkey()
        self.assertFalse(self.panel.isVisible())
        self.panel.poll_menu_hotkey()  # Held is not a second press.
        self.assertFalse(self.panel.isVisible())
        pressed.clear();self.panel.poll_menu_hotkey()
        pressed.add(0xA1);self.panel.poll_menu_hotkey()
        self.assertTrue(self.panel.isVisible())

    def test_custom_menu_binding_persists_and_capture_does_not_hide_panel(self):
        self.panel.select_page('Input')
        button = self.panel.binding_buttons['menu_toggle']
        self.assertEqual(button.text(), 'Right Shift')
        self.panel.begin_capture('menu_toggle', button)
        QTest.keyClick(button, Qt.Key.Key_F4)
        self.assertEqual(self.panel.model.config.keys['menu_toggle'], 0x73)
        self.assertEqual(button.text(), 'F4')
        self.assertTrue(self.panel.isVisible())
        self.panel.model.save()
        from native.gui_model import SettingsModel
        restored = SettingsModel(self.temp.name)
        self.assertEqual(restored.config.keys['menu_toggle'], 0x73)

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
