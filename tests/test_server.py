"""Isolated HTTP/store tests; never writes to the real data directory."""
import http.client
import ipaddress
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server


class ServerTests(unittest.TestCase):
    def test_today_survives_concurrent_slow_sources_and_reuses_work(self):
        gate = threading.Event()

        def slow():
            gate.wait(1)
            raise server.SourceUnavailable('offline')

        try:
            with patch.object(self.hub, 'calendar', side_effect=lambda *args: slow()) as calendar, \
                 patch.object(self.hub, 'weather', side_effect=slow) as weather, \
                 patch.object(server, 'TODAY_TIMEOUT', 0.02):
                started = time.monotonic()
                for _ in range(2):
                    status, _, raw = self.request('/api/today')
                    data = json.loads(raw)
                    self.assertEqual(status, 200)
                    self.assertEqual(data['calendarSource'], 'failed')
                    self.assertEqual(data['weather']['source'], 'failed')
                    self.assertIn('shoppingOpen', data)
                    self.assertEqual({a['view'] for a in data['alerts'] if a.get('id', '').endswith('-offline')},
                                     {'calendar', 'weather'})
                    self.assertTrue(all(a['severity'] == 'error' for a in data['alerts'] if a.get('id', '').endswith('-offline')))
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertEqual(calendar.call_count, 1)
                self.assertEqual(weather.call_count, 1)
        finally:
            gate.set()

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

    def test_recipe_import_is_bounded_saved_and_reopened_without_fetch(self):
        with patch.object(server, 'read_recipe') as read:
            for i in range(7):
                read.return_value={'title':'Synthetic recipe','url':'https://example.com/r'+str(i),
                                   'ingredients':['one ingredient'],'steps':['one step']}
                item=self.api('/api/recipes','POST',{'url':'https://example.com/r'+str(i)})
                self.assertEqual(item['title'],'Synthetic recipe')
            saved=self.api('/api/recipes')['recipes']
            self.assertEqual(len(saved),5)
            self.assertEqual(saved[0]['url'],'https://example.com/r6')
            self.assertEqual(read.call_count,7)
        status,_,_=self.request('/api/recipes','POST',{'url':'http://127.0.0.1'})
        self.assertEqual(status,400)

    def test_recipe_http_crud_revision_and_offline_reader(self):
        value={'title':'Test soup','ingredients':['water'],'steps':['Simmer'], 'tags':['Soup']}
        row=self.api('/api/recipes','POST',{'recipe':value})
        path='/api/recipes/'+row['id']
        self.assertTrue(row['saved'])
        changed=self.api(path,'PATCH',{'revision':1,'recipe':dict(value,title='Edited soup')})
        self.assertEqual(changed['revision'],2)
        self.assertEqual(self.request(path,'PATCH',{'revision':1,'saved':True})[0],409)
        self.assertEqual(self.request(path,'DELETE',{'revision':1})[0],409)
        self.assertEqual(self.api(path)['title'],'Edited soup')
        self.assertNotIn('ingredients',self.api('/api/recipes')['recipes'][0])
        self.api(path,'DELETE',{'revision':2})
        self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request(path,'DELETE',{'revision':2})[0],404)
        # Auth boundary covers new routes just as it covers shopping.
        with patch.object(self.handler,'allowed',return_value=False):
            with patch.object(self.hub.recipes,'change') as change:
                # Exercise handler directly: allowed() returning False sends no response.
                handler=object.__new__(self.handler)
                handler.do_PATCH()
                handler.do_DELETE()
                change.assert_not_called()

    def test_legacy_recipe_http_edit_above_new_body_limit(self):
        legacy={'id':'012345abcdef','title':'Legacy','ingredients':['Water'], 'steps':['x'*2000]*20, 'yield':'x'*100}
        self.hub.store.write('recipes',[legacy])
        row=self.api('/api/recipes/'+legacy['id'])
        row['title']='Legacy edited'
        edited=self.api('/api/recipes/'+legacy['id'],'PATCH',{'revision':1,'recipe':row})
        self.assertEqual(edited['title'],'Legacy edited')
        self.assertEqual(edited['steps'],legacy['steps'])
        self.assertEqual(self.request('/api/recipes','POST',{'recipe':legacy})[0],400)

    def test_recipe_concurrent_edits_only_one_wins(self):
        from concurrent.futures import ThreadPoolExecutor
        row=self.api('/api/recipes','POST',{'recipe':{'title':'Soup','ingredients':['Water'],'steps':['Simmer']}})
        path='/api/recipes/'+row['id']
        def update(title):
            return self.request(path,'PATCH',{'revision':1,'recipe':{'title':title,'ingredients':['Water'],'steps':['Simmer']}})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(update,['First','Second']))
        self.assertEqual(sorted(statuses),[200,409])
        self.assertEqual(self.api(path)['revision'],2)

    def test_homepage_quote_rotates_daily(self):
        day=server.now()
        with patch.object(server,'now',return_value=day):
            first=self.api('/api/today')['quote']
        with patch.object(server,'now',return_value=day+timedelta(days=1)):
            second=self.api('/api/today')['quote']
        self.assertEqual(first,server.QUOTES[day.toordinal()%len(server.QUOTES)])
        self.assertNotEqual(first,second)

    def test_local_tracker_route_has_admission_and_restrictive_csp(self):
        with patch.object(server.recipe_tracker,'response',return_value=(b'<h1>Recipe Tracker</h1>','text/html')) as app:
            status,headers,raw=self.request('/recipe_tracker/')
            self.assertEqual(status,200)
            self.assertIn("connect-src 'none'",headers['Content-Security-Policy'])
            self.assertEqual(raw,b'<h1>Recipe Tracker</h1>')
        self.assertEqual(self.request('/recipe_tracker/../../config.json')[0],404)

    def test_get_endpoints_and_static(self):
        paths = ['/api/today', '/api/calendar?from=' + server.iso(server.now()),
                 '/api/shopping', '/api/weather', '/api/photos/manifest',
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
        self.assertEqual(self.request('/api/quotes')[0], 404)

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

    def test_photo_manifest_routes_and_stale_status(self):
        from aura_sync import atomic_json
        from photos import PhotoLibrary
        root = server.Path(self.temp.name) / 'photos'
        (root / 'cache').mkdir(parents=True)
        pid = 'a' * 32
        atomic_json(root / 'manifest.json', {'photos': [{'id': pid}], 'syncedAt': server.iso(server.now())})
        atomic_json(root / 'status.json', {'state': 'current'})
        (root / 'cache' / (pid + '.jpg')).write_bytes(b'display-jpeg')
        (root / 'cache' / (pid + '.thumb.jpg')).write_bytes(b'thumb-jpeg')
        self.hub.photos = PhotoLibrary(root, enabled=True)
        manifest = self.api('/api/photos/manifest')
        self.assertEqual(manifest['source'], 'aura')
        self.assertEqual(manifest['photos'][0]['id'], pid)
        status, headers, raw = self.request('/photos/' + pid)
        self.assertEqual((status, headers['Content-Type'], raw), (200, 'image/jpeg', b'display-jpeg'))
        self.assertEqual(self.request('/photos/' + pid + '.thumb')[2], b'thumb-jpeg')
        self.assertEqual(self.request('/photos/' + 'b' * 32)[0], 404)
        atomic_json(root / 'status.json', {'state': 'failed'})
        self.assertEqual(self.api('/api/photos/manifest')['state'], 'stale')
        sources = self.api('/api/status')['sources']
        self.assertEqual(next(s for s in sources if s['id'] == 'photos')['state'], 'stale')

    def test_slow_cloud_does_not_delay_or_disable_working_home_assistant(self):
        from unittest.mock import Mock
        from govee import GoveeCloud
        gate=threading.Event()
        cloud=GoveeCloud([{'sku':'H6008','device':'00:00:00:00:00:00:00:01'}],'synthetic-govee-key')
        self.hub.govee=cloud
        ha=Mock()
        def home():
            time.sleep(.05)
            return {'source':'homeassistant','lights':[{'id':'local','available':True,'on':True}]}
        ha.home.side_effect=home;self.hub.integrations=ha
        def read(entry):
            gate.wait(1)
            raise server.SourceUnavailable('synthetic cloud outage')
        try:
            with patch.object(cloud,'read',side_effect=read):
                start=time.monotonic();status,_,raw=self.request('/api/home')
                self.assertLess(time.monotonic()-start,.25)
                data=json.loads(raw);self.assertEqual(status,200)
                self.assertTrue(data['lights'][0]['available'])
                self.assertFalse(data['lights'][1]['available'])
        finally:
            gate.set();cloud.pool.shutdown(wait=True,cancel_futures=True)

    def test_live_camera_routes_require_json_and_never_cache_or_forward_queries(self):
        from unittest.mock import Mock
        from integrations import CameraInactive
        sid='a'*32
        live=Mock()
        live.stop.return_value={'stopped':True}
        live.start.return_value={'url':'/camera/live/'+sid+'/master_playlist.m3u8'}
        live.resource.return_value=(b'#EXTM3U\n','application/vnd.apple.mpegurl')
        self.hub.live_camera=live
        self.assertEqual(self.request('/api/camera/live','POST',{'id':'b'*16},content_type='text/plain')[0],400)
        live.start.assert_not_called()
        self.assertEqual(self.request('/api/camera/live','POST',{'id':'b'*16})[0],200)
        live.start.assert_called_once_with('b'*16)
        route='/camera/live/'+sid+'/master_playlist.m3u8'
        status,headers,raw=self.request(route)
        self.assertEqual((status,headers['Cache-Control'],raw),(200,'no-store',b'#EXTM3U\n'))
        self.assertEqual(self.request(route+'?_HLS_msn=1')[0],404)
        live.resource.assert_called_once_with(sid,'master_playlist.m3u8')
        live.resource.side_effect=CameraInactive('Camera unavailable')
        self.assertEqual(self.request(route)[0],410)
        self.assertEqual(self.request('/api/camera/stop','POST',{'session':sid})[0],200)
        live.stop.assert_called_once_with(sid)

    def test_camera_snapshot_route_stays_authenticated_and_uncached(self):
        from integrations import HomeAssistant
        self.hub.integrations = HomeAssistant({'cameras': [{'entity': 'camera.test'}]}, 'synthetic-camera-token')
        alias = self.hub.integrations.alias('camera.test')
        with patch.object(self.hub.integrations, 'camera_image', return_value=b'jpeg-image') as camera:
            status, headers, raw = self.request('/camera/' + alias + '.jpg')
            self.assertEqual((status, headers['Content-Type'], raw), (200, 'image/jpeg', b'jpeg-image'))
            self.assertEqual(headers['Cache-Control'], 'no-store')
            camera.assert_called_once_with(alias)
            with patch.object(self.handler, 'allowed', return_value=False):
                denied = object.__new__(self.handler)
                denied.path = '/camera/' + alias + '.jpg'
                denied.do_GET()
            camera.assert_called_once_with(alias)

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
        token = 'T' * 43
        lan = [ipaddress.ip_network('192.0.2.0/24')]
        for peer, cookie, expected in [('127.0.0.1', '', True), ('192.0.2.10', '', False),
                                       ('192.0.2.10', 'hub_device=' + 'X' * 43, False),
                                       ('192.0.2.10', 'other=1; hub_device=' + token, True),
                                       ('198.51.100.7', 'hub_device=' + token, False)]:
            handler = object.__new__(server.make_handler(self.hub, lan, token))
            handler.client_address = (peer, 123)
            handler.headers = {'Cookie': cookie}
            with patch.object(handler, 'send_error'):
                self.assertEqual(handler.allowed(), expected, (peer, cookie))
        for method in ['GET', 'HEAD', 'POST', 'PATCH', 'DELETE']:
            with patch.object(self.handler, 'allowed', return_value=False):
                # Verify each method exits before parsing data or serving files.
                handler = object.__new__(self.handler)
                handler.path = '/api/settings'
                with patch.object(handler, 'reply') as reply:
                    getattr(handler, 'do_' + method)()
                    reply.assert_not_called()

    def test_pairing_sets_http_only_cookie(self):
        token = 'P' * 43
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(self.hub, [], token))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            def get(path):
                conn = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
                conn.request('GET', path)
                response = conn.getresponse()
                response.read()
                conn.close()
                return response.status, dict(response.getheaders())
            for path in ['/pair', '/pair?token=wrong', '/pair?token=' + token + '&token=' + token]:
                self.assertEqual(get(path)[0], 403, path)
            self.assertEqual(get('/pair?a=1&b=2&c=3')[0], 400)
            status, headers = get('/pair?token=' + token)
            self.assertEqual(status, 302)
            self.assertEqual(headers['Location'], '/')
            self.assertIn('hub_device=' + token, headers['Set-Cookie'])
            self.assertIn('HttpOnly', headers['Set-Cookie'])
            self.assertIn('SameSite=Strict', headers['Set-Cookie'])
            self.assertEqual(headers['Cache-Control'], 'no-store')
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()

    def test_load_token_creates_private_file(self):
        path = server.Path(self.temp.name) / 'cfg' / 'device-token'
        token = server.load_token(path)
        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(server.load_token(path), token)
        path.chmod(0o644)
        with self.assertRaises(SystemExit):
            server.load_token(path)
        path.chmod(0o600)
        path.write_text('short\n')
        with self.assertRaises(SystemExit):
            server.load_token(path)


if __name__ == '__main__':
    unittest.main()
