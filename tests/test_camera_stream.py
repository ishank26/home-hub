import gzip
import io
import time
import unittest
from email.message import Message
from unittest.mock import patch
from integrations import HomeAssistant, CameraInactive, SourceUnavailable
from camera_stream import LiveCamera, rewrite_manifest, stream_url

SID='a'*32
class Response(io.BytesIO):
    def __init__(self, raw, encoding='identity'):
        super().__init__(raw); self.headers=Message(); self.headers['Content-Encoding']=encoding

class StreamTests(unittest.TestCase):
    def setUp(self):
        self.ha=HomeAssistant({'cameras':[{'entity':'camera.test'}]},'synthetic-stream-token')
        self.live=LiveCamera(self.ha)
        self.state=patch.object(self.ha,'read_state',return_value={'state':'idle'})
        self.state.start();self.addCleanup(self.state.stop)
        self.start=patch('camera_stream.stream_url',return_value='/api/hls/'+'b'*32+'/')
        self.start.start();self.addCleanup(self.start.stop)
        self.url=self.live.start(self.ha.alias('camera.test'))['url'];self.sid=self.url.split('/')[3]

    def test_manifest_rewrites_all_supported_references(self):
        raw=b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXT-X-PART:URI="./segment/12.2.m4s",DURATION=1\n./segment/12.m4s\nplaylist.m3u8\n'
        rewritten=rewrite_manifest(raw,SID).decode()
        self.assertNotIn('EXT-X-PART:',rewritten)
        self.assertIn('URI="/camera/live/'+SID+'/init.mp4"',rewritten)
        self.assertIn('/camera/live/'+SID+'/playlist.m3u8',rewritten)

    def test_rejects_foreign_traversal_query_key_variable_and_unquoted_uris(self):
        for uri in ('https://example.invalid/a','//example.invalid/a','../init.mp4','./../init.mp4',
                    '/api/hls/private/init.mp4','segment/1.m4s?x=1','%2e%2e/init.mp4','${secret}'):
            for line in (uri, '#EXT-X-MAP:URI="'+uri+'"'):
                with self.assertRaises(ValueError):rewrite_manifest(('#EXTM3U\n'+line+'\n').encode(),SID)
        for line in ('#EXT-X-KEY:METHOD=AES-128,URI="init.mp4"','#EXT-X-MAP:URI=init.mp4'):
            with self.assertRaises(ValueError):rewrite_manifest(('#EXTM3U\n'+line).encode(),SID)

    def test_only_one_viewer_old_and_expired_sessions_fail(self):
        new=self.live.start(self.ha.alias('camera.test'))['url'].split('/')[3]
        with self.assertRaises(CameraInactive):self.live.resource(self.sid,'init.mp4')
        self.live.session['used']=time.monotonic()-46
        with self.assertRaises(CameraInactive):self.live.resource(new,'init.mp4')
        self.assertIsNone(self.live.session)

    def test_privacy_checked_for_every_resource_and_after_upstream_read(self):
        for name in ('playlist.m3u8','init.mp4','segment/2.m4s'):
            self.ha.read_state.return_value={'state':'off'}
            with patch.object(self.ha.transport,'open') as transport:
                with self.assertRaises(CameraInactive):self.live.resource(self.sid,name)
                transport.assert_not_called()
            self.assertIsNone(self.live.session)
            self.ha.read_state.return_value={'state':'idle'}
            self.sid=self.live.start(self.ha.alias('camera.test'))['url'].split('/')[3]
        def disable(*a,**kw):
            self.ha.read_state.return_value={'state':'off'}
            return Response(b'fragment')
        with patch.object(self.ha.transport,'open',side_effect=disable):
            with self.assertRaises(CameraInactive):self.live.resource(self.sid,'init.mp4')

    def test_fixed_endpoint_credentials_only_header_and_bounded_gzip(self):
        data=b'#EXTM3U\nplaylist.m3u8\n'
        with patch.object(self.ha.transport,'open',return_value=Response(gzip.compress(data),'gzip')) as request:
            raw,kind=self.live.resource(self.sid,'master_playlist.m3u8')
        req=request.call_args.args[0]
        self.assertNotIn('synthetic-stream-token',req.full_url)
        self.assertEqual(req.get_header('Authorization'),'Bearer synthetic-stream-token')
        self.assertTrue(req.full_url.startswith('http://127.0.0.1:8123/api/hls/'))
        self.assertNotIn('/api/hls/',raw.decode())
        with patch.object(self.ha.transport,'open',return_value=Response(gzip.compress(b'x'*70000),'gzip')):
            with self.assertRaises(SourceUnavailable):self.live.resource(self.sid,'playlist.m3u8')

    def test_low_latency_capabilities_removed_for_polling_only_player(self):
        raw=b'#EXTM3U\n#EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES\n#EXT-X-START:TIME-OFFSET=-2\n#EXT-X-PART-INF:PART-TARGET=1\n#EXT-X-PRELOAD-HINT:URI="./segment/2.1.m4s"\n./segment/1.m4s\n'
        rewritten=rewrite_manifest(raw,SID)
        for marker in (b'SERVER-CONTROL',b'EXT-X-START',b'PART-INF',b'PRELOAD-HINT'):
            self.assertNotIn(marker,rewritten)
        self.assertIn(b'/segment/1.m4s',rewritten)

    def test_concurrency_and_stop_bounds(self):
        self.live.readers.acquire();self.live.readers.acquire()
        try:
            with self.assertRaises(SourceUnavailable):self.live.resource(self.sid,'init.mp4')
        finally:self.live.readers.release();self.live.readers.release()
        self.live.stop(self.sid)
        with self.assertRaises(CameraInactive):self.live.resource(self.sid,'init.mp4')
        self.assertIsNone(self.live.session)

    def test_websocket_auth_uses_preconnected_loopback_even_with_proxy_environment(self):
        import os, sys
        from unittest.mock import MagicMock
        ws=MagicMock()
        ws.recv.side_effect=['{"type":"auth_required"}','{"type":"auth_ok"}',
            '{"id":1,"success":true,"result":{"url":"/api/hls/'+('c'*32)+'/master_playlist.m3u8"}}']
        module=MagicMock();module.create_connection.return_value=ws
        direct=MagicMock()
        with patch.dict(os.environ,{'http_proxy':'http://example.invalid:8080','https_proxy':'http://example.invalid:8080','NO_PROXY':''}), patch.dict(sys.modules,{'websocket':module}), patch('camera_stream.socket.create_connection',return_value=direct) as connect:
            # Bypass the setup patch to exercise the real helper under hostile env.
            self.start.stop()
            try:prefix=stream_url(self.ha,'camera.test')
            finally:self.start.start()
        connect.assert_called_once_with(('127.0.0.1',8123),timeout=6)
        self.assertIs(module.create_connection.call_args.kwargs['socket'],direct)
        self.assertEqual(prefix,'/api/hls/'+('c'*32)+'/')
        direct.close.assert_called_once()
        self.assertNotIn('synthetic-stream-token',str(module.create_connection.call_args))

    def test_cold_upstream_503_can_recover_in_same_session(self):
        from urllib.error import HTTPError
        with patch.object(self.ha.transport,'open',side_effect=[HTTPError('synthetic',503,'',{},None),Response(b'#EXTM3U\nplaylist.m3u8\n')]):
            with self.assertRaises(SourceUnavailable) as error:
                self.live.resource(self.sid,'master_playlist.m3u8')
            self.assertNotIsInstance(error.exception,CameraInactive)
            self.assertEqual(self.live.session['id'],self.sid)
            raw,_=self.live.resource(self.sid,'master_playlist.m3u8')
            self.assertIn(b'playlist.m3u8',raw)
