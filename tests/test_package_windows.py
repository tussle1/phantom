from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from tools.package_windows import check_pe, package
from native.presets import PRESETS, preset_document, preset_filename


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.exe = self.directory/'fixture.exe'
        # Header fixture only: never distributed or represented as a runnable program.
        header = bytearray(256)
        header[:2] = b'MZ'
        struct.pack_into('<I', header, 0x3C, 128)
        header[128:132] = b'PE\0\0'
        struct.pack_into('<H', header, 132, 0x8664)
        struct.pack_into('<H', header, 152, 0x20B)
        self.exe.write_bytes(header)

    def test_reject_source_renamed_exe(self):
        self.exe.write_text('print("not an executable")')
        with self.assertRaises(ValueError):
            check_pe(self.exe)

    def test_reject_x86(self):
        data = bytearray(self.exe.read_bytes())
        struct.pack_into('<H', data, 132, 0x14C)
        self.exe.write_bytes(data)
        with self.assertRaises(ValueError):
            check_pe(self.exe)

    def test_reject_out_of_bounds_pe(self):
        data = bytearray(self.exe.read_bytes())
        struct.pack_into('<I', data, 0x3C, 0xFFFF)
        self.exe.write_bytes(data)
        with self.assertRaises(ValueError):
            check_pe(self.exe)

    def test_requires_source_revision(self):
        with self.assertRaises(ValueError):
            package(self.exe, self.directory/'test.zip', 'main')

    def test_foundation_dll_is_included_and_hashed(self):
        dll = self.directory/'fixture-foundation.dll'
        dll.write_bytes(self.exe.read_bytes())
        output = self.directory/'test.zip'
        with redirect_stdout(io.StringIO()):
            package(self.exe, output, 'a'*40, dll)
        with zipfile.ZipFile(output) as archive:
            self.assertIn('phantom-cpp/phantom-internal-foundation.dll', archive.namelist())
            self.assertIn('phantom-cpp/README.md', archive.namelist())
            self.assertIn('phantom-cpp/include/phantom/api.h', archive.namelist())
            self.assertIn('phantom-cpp/include/phantom/runtime.h', archive.namelist())
            manifest = json.loads(archive.read('BUILD.json'))
            self.assertTrue(manifest['cpp_foundation_included'])
            self.assertEqual(manifest['cpp_foundation_sha256'],
                             hashlib.sha256(archive.read('phantom-cpp/phantom-internal-foundation.dll')).hexdigest())

    def test_contents_and_executable_digest(self):
        output = self.directory/'test.zip'
        with redirect_stdout(io.StringIO()):
            package(self.exe, output, 'a'*40)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {
                'phantom-native.exe', 'offset-profile.json', 'README.md', 'run.cmd',
                'RUN-ME.txt', 'CONFIG.example.json', 'BUILD.json', 'FONT-LICENSE.txt'} |
                {'presets/'+preset_filename(name) for name in PRESETS})
            self.assertIsNone(archive.testzip())
            for name in PRESETS:
                self.assertEqual(json.loads(archive.read('presets/'+preset_filename(name))), preset_document(name))
            manifest = json.loads(archive.read('BUILD.json'))
            self.assertEqual(manifest['app_version'], '1.2.0')
            self.assertIn(b'v1.2.0', archive.read('RUN-ME.txt'))
            self.assertFalse(manifest['game_behavior_verified'])
            self.assertEqual(manifest['source_commit'], 'a'*40)
            self.assertEqual(manifest['executable_sha256'], hashlib.sha256(archive.read('phantom-native.exe')).hexdigest())
            self.assertIn(b'--profile', archive.read('run.cmd'))
            self.assertFalse(json.loads(archive.read('CONFIG.example.json'))['settings']['trigger'])


if __name__ == '__main__':
    unittest.main()
