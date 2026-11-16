from dataclasses import asdict
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import patch

from native.config import Config
from native.gui_model import SettingsModel
from native.session import RuntimeSession


class GuiModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = SettingsModel(self.temp.name)

    def test_defaults_do_not_enable_input(self):
        self.assertEqual(self.model.config.aim, 'off')
        self.assertFalse(self.model.config.trigger)
        self.assertEqual(self.model.names(), [])

    def test_invalid_change_is_transactional(self):
        before = self.model.document()
        with self.assertRaises(ValueError):
            self.model.set('aim_fov', 999)
        self.assertEqual(self.model.document(), before)
        self.assertEqual(self.model.revision, 0)
        with self.assertRaises(ValueError):
            self.model.set('silent', True)

    def test_save_load_named(self):
        self.model.set('aim_fov', 5)
        self.model.save('practice')
        self.model.set('aim_fov', 10)
        self.model.load('practice')
        self.assertEqual(self.model.config.aim_fov, 5)
        self.assertEqual(self.model.names(), ['practice'])
        self.assertEqual(self.model.name, 'practice')
        self.assertEqual(self.model.path.name, 'practice.json')

    def test_bad_load_keeps_current_config(self):
        before = self.model.document()
        Path(self.temp.name, 'bad.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.model.load('bad')
        self.assertEqual(self.model.document(), before)
        self.assertEqual(self.model.name, 'default')

    def test_keys_and_reset(self):
        self.model.set_key('aim_hold', 0x06)
        self.assertEqual(self.model.config.keys['aim_hold'], 0x06)
        with self.assertRaises(ValueError):
            self.model.set_key('exit', self.model.config.keys['save'])
        self.model.set('aim_fov', 10)
        self.model.reset('aim_fov')
        self.assertEqual(self.model.config.aim_fov, Config().aim_fov)

    def test_stale_runtime_reports_cannot_overwrite_newer_ui(self):
        self.model.set('aim_fov', 8)
        self.assertFalse(self.model.accept_runtime(asdict(Config()), 0))
        self.assertEqual(self.model.config.aim_fov, 8)
        settings = asdict(Config());settings['skeleton'] = False
        self.assertTrue(self.model.accept_runtime(settings, self.model.revision))
        self.assertFalse(self.model.config.skeleton)

    def test_invalid_runtime_report_is_not_applied(self):
        with self.assertRaises(ValueError):
            self.model.accept_runtime({}, 100)
        self.assertEqual(self.model.revision, 0)


class SessionTests(unittest.TestCase):
    def test_menu_visibility_controls_a_separate_pause_event(self):
        session = RuntimeSession()
        session.pause_event = threading.Event()
        session.set_menu_visible(True)
        self.assertTrue(session.pause_event.is_set())
        session.set_menu_visible(False)
        self.assertFalse(session.pause_event.is_set())
        self.assertFalse(session.menu_visible)

    def test_no_process_poll_is_safe(self):
        session = RuntimeSession()
        self.assertFalse(session.running)
        self.assertEqual(session.poll(), [])
        session.stop()
        session.update(asdict(Config()), 0)
        self.assertIsNone(session.pending)

    def test_queue_full_coalesces_instead_of_blocking(self):
        session = RuntimeSession()
        class Process:
            def is_alive(self): return True
        session.process = Process()
        session.commands = queue.Queue(maxsize=1)
        session.commands.put({'old': True})
        session.update(asdict(Config()), 1)
        self.assertEqual(session.pending['revision'], 1)
        session.update(asdict(Config()), 2)
        self.assertEqual(session.pending['revision'], 2)
        session.commands.get_nowait()
        session.flush()
        self.assertEqual(session.commands.get_nowait()['revision'], 2)
        self.assertIsNone(session.pending)

    def test_negative_revision_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeSession().update(asdict(Config()), -1)

    def test_non_windows_start_does_not_spawn(self):
        with patch('native.session.sys.platform', 'linux'):
            with self.assertRaises(OSError):
                RuntimeSession().start('missing', {'version': 1, 'settings': asdict(Config())}, Path('missing'))


if __name__ == '__main__':
    unittest.main()
