from dataclasses import asdict
import hashlib
from pathlib import Path
import unittest

from native.config import Config, validate_config
from native.hotkeys import MenuHotkey, capture_vk, keys_conflict


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.pressed = set()
        self.hotkey = MenuHotkey(lambda vk: vk in self.pressed)
        self.hotkey.prime(0xA1)

    def test_right_shift_only_and_one_toggle_per_press(self):
        self.pressed.add(0xA0)
        self.assertFalse(self.hotkey.poll(0xA1))
        self.pressed.add(0xA1)
        self.assertTrue(self.hotkey.poll(0xA1))
        self.assertFalse(self.hotkey.poll(0xA1))
        self.assertFalse(self.hotkey.poll(0xA1))
        self.pressed.remove(0xA1)
        self.assertFalse(self.hotkey.poll(0xA1))
        self.pressed.add(0xA1)
        self.assertTrue(self.hotkey.poll(0xA1))

    def test_capture_blocks_toggle_and_does_not_replay_it(self):
        self.pressed.add(0xA1)
        self.assertFalse(self.hotkey.poll(0xA1, blocked=True))
        self.assertFalse(self.hotkey.poll(0xA1))
        self.pressed.clear()
        self.hotkey.poll(0xA1)
        self.pressed.add(0xA1)
        self.assertTrue(self.hotkey.poll(0xA1))

    def test_rebinding_while_held_waits_for_release(self):
        self.pressed.add(0x2D)
        self.assertFalse(self.hotkey.poll(0x2D))
        self.assertFalse(self.hotkey.poll(0x2D))
        self.pressed.clear();self.hotkey.poll(0x2D)
        self.pressed.add(0x2D)
        self.assertTrue(self.hotkey.poll(0x2D))

    def test_modifier_side_capture(self):
        self.assertEqual(capture_vk(0x01000020, 0x10, 0x36), 0xA1)
        self.assertEqual(capture_vk(0x01000020, 0x10, 0x2A), 0xA0)
        self.assertEqual(capture_vk(0x01000020, 0xA1, 0), 0xA1)
        self.assertEqual(capture_vk(0x01000021, 0x11, 0x11D), 0xA3)
        self.assertEqual(capture_vk(0x01000023, 0x12, 0x138), 0xA5)
        self.assertEqual(capture_vk(0x01000033), 0x73)  # F4, Qt-only synthetic event.
        self.assertEqual(capture_vk(0x41), 0x41)
        self.assertEqual(capture_vk(999999), 0)

    def test_modifier_alias_conflicts(self):
        for a,b in ((0x10,0xA1),(0xA1,0x10),(0x11,0xA2),(0x12,0xA5),(0xA1,0xA1)):
            self.assertTrue(keys_conflict(a,b))
        self.assertFalse(keys_conflict(0xA0,0xA1))
        settings = asdict(Config());settings['keys']['aim_hold'] = 0x10
        with self.assertRaises(ValueError):
            validate_config({'version':1,'settings':settings})
        settings['keys']['aim_hold'] = 0xA0
        self.assertEqual(validate_config({'version':1,'settings':settings}).keys['menu_toggle'],0xA1)

    def test_default_and_legacy_config_upgrade(self):
        self.assertEqual(Config().keys['menu_toggle'],0xA1)
        settings = asdict(Config());settings['keys'].pop('menu_toggle')
        upgraded = validate_config({'version':1,'settings':settings})
        self.assertEqual(upgraded.keys['menu_toggle'],0xA1)
        self.assertNotIn('menu_toggle', settings['keys'])  # Caller data is not mutated.
        settings['keys']['aim_hold'] = 0x10
        upgraded = validate_config({'version':1,'settings':settings})
        self.assertEqual(upgraded.keys['menu_toggle'],0x2D)
        self.assertEqual(upgraded.keys['aim_hold'],0x10)

    def test_poppins_asset_and_license_are_complete(self):
        directory = Path(__file__).resolve().parents[1]/'native/assets/fonts'
        data = (directory/'Poppins-Regular.ttf').read_bytes()
        self.assertEqual(data[:4], b'\0\x01\0\0')
        git_blob = b'blob '+str(len(data)).encode()+b'\0'+data
        self.assertEqual(hashlib.sha1(git_blob).hexdigest(),'0bda228ade88b0bb5aac7da2c881d0c3f64d0817')
        self.assertIn('SIL OPEN FONT LICENSE', (directory/'OFL.txt').read_text())


if __name__ == '__main__':
    unittest.main()
