"""Isolated HTTP/store tests; never writes to the real data directory."""
import http.client
import ipaddress
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hub = server.Hub(server.Store(self.temp.name))
        self.handler = server.make_handler(self.hub, [])
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method='GET', body=None, content_type='application/json', raw=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        payload = raw if raw is not None else json.dumps(body) if body is not None else None
        conn.request(method, path, body=payload, headers={'Content-Type': content_type})
        response = conn.getresponse()
        data = response.read()
        status, headers = response.status, dict(response.getheaders())
        conn.close()
        return status, headers, data

    def api(self, path, method='GET', body=None):
        status, _, data = self.request(path, method, body)
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def test_get_endpoints_and_static(self):
        paths = ['/api/today', '/api/calendar?from=' + server.iso(server.now()),
                 '/api/shopping', '/api/weather', '/api/quotes', '/api/photos/manifest',
                 '/api/home', '/api/settings', '/api/status']
        for path in paths:
            with self.subTest(path=path):
                status, headers, data = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], 'application/json')
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertIsInstance(json.loads(data), dict)
                self.assertNotIn('Access-Control-Allow-Origin', headers)
        for path in ['/', '/app.css', '/app.js', '/photos/p00.svg']:
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/api/missing')[0], 404)

    def test_shopping_lifecycle_and_persistence(self):
        result = self.api('/api/shopping', 'POST', {'name': '  Test apples  ', 'qty': '2', 'notes': 'ripe', 'category': 'Unknown'})
        item = result['items'][-1]
        self.assertEqual((item['name'], item['category'], item['notes']), ('Test apples', 'Other', 'ripe'))
        self.assertFalse(item['done'])
        self.api('/api/shopping/' + item['id'], 'PATCH', {'done': True})
        restored = server.Hub(server.Store(self.temp.name))
        self.assertTrue(restored.shopping()['items'][-1]['done'])
        self.api('/api/shopping/clear', 'POST', {})
        self.assertNotIn(item['id'], [i['id'] for i in self.hub.shopping()['items']])
        item = self.api('/api/shopping', 'POST', {'name': 'Delete me'})['items'][-1]
        self.api('/api/shopping/' + item['id'], 'DELETE', {})
        self.assertNotIn(item['id'], [i['id'] for i in self.hub.shopping()['items']])

    def test_write_validation(self):
        for body in [{'name': ''}, {'name': ' '}, {'name': 'x' * 61}, {'name': 'bad\nx'},
                     {'name': '\x00bad'}, {'name': None}, {'name': 123},
                     {'name': 'Valid', 'notes': 'x' * 121}, {'name': 'Valid', 'qty': []}]:
            with self.subTest(body=body):
                self.assertEqual(self.request('/api/shopping', 'POST', body)[0], 400)
        item = self.api('/api/shopping')['items'][0]
        self.assertEqual(self.request('/api/shopping/' + item['id'], 'PATCH', {'done': 1})[0], 400)
        self.assertEqual(self.request('/api/shopping/aaaaaaaaaaaa', 'PATCH', {'done': True})[0], 400)
        self.assertEqual(self.request('/api/shopping/invalid', 'DELETE', {})[0], 404)
        for raw in ['[]', 'null', '{', 'x' * (server.MAX_BODY + 1)]:
            self.assertEqual(self.request('/api/shopping', 'POST', raw=raw)[0], 400)

    def test_csrf_content_type_and_preflight(self):
        for method, path in [('POST', '/api/shopping'), ('PATCH', '/api/shopping/' + self.hub.shopping()['items'][0]['id']), ('DELETE', '/api/shopping/' + self.hub.shopping()['items'][0]['id'])]:
            for content_type in ['text/plain', 'application/x-www-form-urlencoded']:
                self.assertEqual(self.request(path, method, {'name': 'Unsafe', 'done': True}, content_type)[0], 400)
        self.assertEqual(self.request('/api/shopping', 'OPTIONS')[0], 501)

    def test_settings_validation_and_bounds(self):
        settings = self.api('/api/settings', 'POST', {'clock24h': True, 'units': 'C', 'idleMinutes': 99, 'photoSeconds': 1, 'returnTodayMinutes': -3, 'quietStart': '21:30'})
        self.assertEqual((settings['idleMinutes'], settings['photoSeconds'], settings['returnTodayMinutes']), (30, 10, 1))
        self.assertEqual(self.api('/api/settings'), settings)
        for body in [{'units': 'K'}, {'quietStart': '25:00'}, {'quietEnd': 'nonsense'}, {'clock24h': 1}, {'photoSeconds': True}, {'unknown': 'x'}]:
            self.assertEqual(self.request('/api/settings', 'POST', body)[0], 400)
        self.assertEqual(server.Hub(server.Store(self.temp.name)).settings(), settings)

    def test_calendar_validation_and_limits(self):
        for path in ['/api/calendar', '/api/calendar?from=invalid', '/api/calendar?from=2026-01-01&days=bad', '/api/today?' + '&'.join(f'a{i}=x' for i in range(9))]:
            self.assertEqual(self.request(path)[0], 400)
        start = server.now()
        result = self.api('/api/calendar?from=' + start.date().isoformat() + '&days=100')
        for event in result['events']:
            self.assertLess(event['start'], server.iso(start + timedelta(days=42)))

    def test_calendar_compares_instants_not_iso_strings(self):
        event = {'id': 'timezone-test', 'start': '2026-10-12T00:30:00+05:30', 'end': '2026-10-12T01:30:00+05:30'}
        with patch.object(server, 'sample_events', return_value=[event]):
            result = self.hub.calendar(datetime.fromisoformat('2026-10-11T18:00:00+00:00'), datetime.fromisoformat('2026-10-11T21:00:00+00:00'))
        self.assertEqual(result['events'], [event])

    def test_home_commands_confirm_state(self):
        self.assertEqual(self.api('/api/home/action', 'POST', {'kind': 'light', 'id': 'living', 'on': False})['result'], 'confirmed')
        self.assertFalse(self.api('/api/home')['lights'][0]['on'])
        self.api('/api/home/action', 'POST', {'kind': 'scene', 'id': 'all_off'})
        self.assertFalse(any(light['on'] for light in self.api('/api/home')['lights']))
        for body in [{'kind': 'light', 'id': 'missing', 'on': True}, {'kind': 'light', 'id': 'living', 'on': 1}, {'kind': 'scene', 'id': 'missing'}, {'kind': 'lock'}]:
            self.assertEqual(self.request('/api/home/action', 'POST', body)[0], 400)

    def test_allowlist_policy(self):
        # A synthetic handler avoids depending on this host's LAN interfaces.
        for networks, peer, expected in [([], '127.0.0.1', True), ([], '::1', True),
                                         ([], '192.0.2.10', False),
                                         (['192.0.2.0/24'], '192.0.2.10', True),
                                         (['192.0.2.10/32'], '192.0.2.11', False)]:
            handler_type = server.make_handler(self.hub, [ipaddress.ip_network(n) for n in networks])
            handler = object.__new__(handler_type)
            handler.client_address = (peer, 123)
            with patch.object(handler, 'send_error') as denied:
                self.assertEqual(handler.allowed(), expected)
                self.assertEqual(denied.called, not expected)
        for method in ['GET', 'HEAD', 'POST', 'PATCH', 'DELETE']:
            with patch.object(self.handler, 'allowed', return_value=False):
                # Verify each method exits before parsing data or serving files.
                handler = object.__new__(self.handler)
                with patch.object(handler, 'reply') as reply:
                    getattr(handler, 'do_' + method)()
                    reply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
