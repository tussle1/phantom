import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from companion import DEFAULTS, MAX_BODY, Server, Store, find_cs2, validate_name, validate_settings


class ValidationTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(validate_settings(DEFAULTS), DEFAULTS)
        self.assertIsNot(validate_settings(DEFAULTS), DEFAULTS)

    def test_reject_invalid_values(self):
        for key, value in [('skeleton', 1), ('pov', True), ('pov', 141), ('pov', 59),
                           ('triggerDelay', -1), ('smoothing', 4.5), ('aimMode', 'other'),
                           ('bone', []), ('recoil', None), ('accent', 'red'),
                           ('aimKey', '<script>'), ('menuKey', 'F13'), ('espRange', 500)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_settings({**DEFAULTS, key: value})
        for value in [None, [], {}, {**DEFAULTS, 'extra': True}]:
            with self.assertRaises(ValueError):
                validate_settings(value)

    def test_names(self):
        for name in ['Legit 01', 'A', 'offline-practice_2']:
            self.assertEqual(validate_name(name), name)
        for name in ['', '../x', '..', '/tmp/x', 'x/y', 'x\\y', 'a\n', 'x'*41, None, 1, ' x', '.hidden']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)

    @unittest.skipIf(sys.platform == 'win32', 'Non-Windows contract')
    def test_no_fake_process(self):
        self.assertIsNone(find_cs2())


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_roundtrip(self):
        self.store.settings['health'] = False
        self.store.save('Night setup')
        self.store.settings['health'] = True
        self.store.load('Night setup')
        self.assertFalse(self.store.settings['health'])
        self.assertEqual(self.store.active, 'Night setup')
        self.assertEqual(self.store.names(), ['Night setup'])
        self.assertEqual(list(Path(self.temp.name).glob('*.tmp')), [])

    def test_corrupt_load_preserves_state(self):
        Path(self.temp.name, 'bad.json').write_text('{"version":1,"settings":{}}')
        with self.assertRaises(ValueError):
            self.store.load('bad')
        self.assertEqual(self.store.settings, DEFAULTS)

    def test_large_load(self):
        Path(self.temp.name, 'large.json').write_text(' '*(MAX_BODY+1))
        with self.assertRaises(ValueError):
            self.store.load('large')

    def test_failed_replace_keeps_previous_file(self):
        self.store.save('good')
        old = Path(self.temp.name, 'good.json').read_bytes()
        self.store.settings['health'] = False
        with patch('companion.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.store.save('good')
        self.assertEqual(Path(self.temp.name, 'good.json').read_bytes(), old)
        self.assertEqual(list(Path(self.temp.name).glob('*.tmp')), [])


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = Server(('127.0.0.1', 0), Store(self.temp.name), demo=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path='/api/state', body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        all_headers = {'Content-Type': 'application/json', 'X-Phantom-Token': self.server.token}
        all_headers.update(headers or {})
        data = raw if raw is not None else json.dumps(body) if body is not None else None
        connection.request('POST' if data is not None else 'GET', path, body=data, headers=all_headers)
        response = connection.getresponse()
        result = response.read()
        status, mime = response.status, response.getheader('Content-Type')
        connection.close()
        return status, json.loads(result) if mime == 'application/json' else result

    def test_state(self):
        status, state = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(state['settings'], DEFAULTS)
        self.assertEqual(state['defaults'], DEFAULTS)
        self.assertFalse(state['capabilities']['injection'])
        self.assertEqual(state['mode'], 'demo')
        self.assertEqual(state['token'], self.server.token)

    def test_settings(self):
        updated = {**DEFAULTS, 'skeleton': False}
        self.assertEqual(self.request('/api/settings', {'settings': updated, 'revision': 0})[0], 200)
        self.assertEqual(self.request()[1]['settings'], updated)
        self.assertEqual(self.request('/api/settings', {'settings': DEFAULTS, 'revision': 0})[0], 409)

    def test_bad_settings(self):
        self.assertEqual(self.request('/api/settings', {'settings': {}, 'revision': 0})[0], 400)
        self.assertEqual(self.request()[1]['revision'], 0)

    def test_missing_revision(self):
        self.assertEqual(self.request('/api/settings', {'settings': DEFAULTS})[0], 409)

    def test_auth(self):
        self.assertEqual(self.request('/api/settings', {}, {'X-Phantom-Token': ''})[0], 403)
        self.assertEqual(self.request('/api/settings', {}, {'X-Phantom-Token': 'wrong'})[0], 403)

    def test_origin(self):
        self.assertEqual(self.request('/api/settings', {}, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/settings', {'settings': DEFAULTS, 'revision': 0}, {'Origin': f'http://127.0.0.1:{self.port}'})[0], 200)

    def test_host(self):
        self.assertEqual(self.request(headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/api/config/save', {}, {'Host': 'evil.example'})[0], 403)

    def test_public_origin(self):
        self.server.public_origin = 'https://test.e2b.app'
        self.assertEqual(self.request(headers={'Host': 'test.e2b.app'})[0], 200)
        self.assertEqual(self.request('/api/settings', {'settings': DEFAULTS, 'revision': 0}, {'Host': 'test.e2b.app', 'Origin': 'https://test.e2b.app'})[0], 200)

    def test_config_lifecycle(self):
        self.assertEqual(self.request('/api/config/save', {'name': 'test', 'revision': 0})[0], 200)
        self.assertEqual(self.request()[1]['configs'], ['test'])
        self.assertEqual(self.request('/api/config/load', {'name': 'test', 'revision': 0})[0], 200)
        self.assertEqual(self.request('/api/config/delete', {'name': 'test', 'revision': 1})[0], 200)
        self.assertEqual(self.request()[1]['configs'], [])
        self.assertIsNone(self.request()[1]['active'])

    def test_hostile_config_name(self):
        self.assertEqual(self.request('/api/config/save', {'name': '../escape', 'revision': 0})[0], 400)

    def test_missing_config(self):
        self.assertEqual(self.request('/api/config/load', {'name': 'missing', 'revision': 0})[0], 404)

    def test_size_and_json(self):
        self.assertEqual(self.request('/api/settings', raw='x'*(MAX_BODY+1))[0], 413)
        self.assertEqual(self.request('/api/settings', raw='{invalid}')[0], 400)
        self.assertEqual(self.request('/api/settings', raw='[]')[0], 400)

    def test_static_and_traversal(self):
        self.assertIn(b'Control room', self.request('/')[1])
        for route in ['/style.css', '/app.js', '/favicon.svg']:
            self.assertEqual(self.request(route)[0], 200)
        self.assertEqual(self.request('/../companion.py')[0], 404)
        self.assertEqual(self.request('/api/missing', {'revision': 0})[0], 404)


if __name__ == '__main__':
    unittest.main()
