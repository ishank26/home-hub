"""Closed camera proxy, byte/decode limits and credentials remaining server-only."""
import io
import unittest
from email.message import Message
from unittest.mock import patch

from integrations import HomeAssistant, CameraInactive, SourceUnavailable, bounded_jpeg


def jpeg(width=400, height=250):
    return (b'\xff\xd8\xff\xc0\x00\x08\x08' + height.to_bytes(2, 'big')
            + width.to_bytes(2, 'big') + b'\x01\xff\xd9')


class ImageResponse(io.BytesIO):
    def __init__(self, body, kind='image/jpeg'):
        super().__init__(body)
        self.headers = Message()
        self.headers['Content-Type'] = kind


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.ha = HomeAssistant({'cameras': [{'entity': 'camera.test', 'name': 'Test camera'}]}, 'synthetic-camera-token')
        self.alias = self.ha.alias('camera.test')
        self.state = patch.object(self.ha, 'read_state', return_value={'state': 'idle', 'attributes': {}})
        self.state.start()
        self.addCleanup(self.state.stop)

    def test_snapshot_fixed_endpoint_no_replayed_bytes_and_server_only_token(self):
        with patch.object(self.ha.transport, 'open', side_effect=lambda *a, **kw: ImageResponse(jpeg())) as request:
            self.assertEqual(self.ha.camera_image(self.alias), jpeg())
            self.assertEqual(self.ha.camera_image(self.alias), jpeg())
        self.assertEqual(request.call_count, 2)
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:8123/api/camera_proxy/camera.test?width=1280&height=800')
        self.assertNotIn('synthetic-camera-token', req.full_url)
        self.assertEqual(req.get_header('Authorization'), 'Bearer synthetic-camera-token')

    def test_unknown_camera_cannot_choose_upstream_url(self):
        with patch.object(self.ha.transport, 'open') as request:
            for value in ['camera.test', 'http://example.invalid', '../camera.test', 'f' * 16]:
                with self.assertRaises(ValueError):
                    self.ha.camera_image(value)
            request.assert_not_called()

    def test_invalid_or_oversized_images_fail_without_serving_old_bytes(self):
        for data, kind in [(b'not-a-jpeg', 'image/jpeg'), (jpeg(), 'text/html'),
                           (jpeg(16000, 16000), 'image/jpeg'), (b'x' * 2_000_001, 'image/jpeg')]:
            with patch.object(self.ha.transport, 'open', return_value=ImageResponse(data, kind)):
                with self.assertRaisesRegex(SourceUnavailable, '^Camera snapshot unavailable$'):
                    self.ha.camera_image(self.alias)

    def test_privacy_transition_stops_delivery_even_after_success(self):
        with patch.object(self.ha.transport, 'open', side_effect=lambda *a, **kw: ImageResponse(jpeg())) as request:
            self.ha.camera_image(self.alias)
            for state in ('off', 'unavailable', 'unknown'):
                self.ha.read_state.return_value = {'state': state, 'attributes': {}}
                with self.assertRaises(CameraInactive):
                    self.ha.camera_image(self.alias)
            self.assertEqual(request.call_count, 1)

    def test_upstream_disabled_response_clears_image(self):
        from urllib.error import HTTPError
        for code in (401, 403, 404, 410, 503):
            with patch.object(self.ha.transport, 'open', side_effect=HTTPError('synthetic', code, '', {}, None)):
                with self.assertRaises(CameraInactive):
                    self.ha.camera_image(self.alias)

    def test_jpeg_header_bounds(self):
        self.assertTrue(bounded_jpeg(jpeg()))
        self.assertFalse(bounded_jpeg(jpeg(0, 250)))
        self.assertFalse(bounded_jpeg(b'\xff\xd8\xff\xe0\xff\xff\xff\xd9'))
        self.assertFalse(bounded_jpeg(jpeg()[:-1]))

    def test_home_never_forwards_camera_picture_tokens(self):
        upstream = {'state': 'idle', 'attributes': {'entity_picture': '/private?token=' + 'x' * 40}}
        with patch.object(self.ha, 'read_state', return_value=upstream):
            result = self.ha.home()
        self.assertEqual(result['cameras'], [{'id': self.alias, 'name': 'Test camera', 'available': True}])
        self.assertNotIn('entity_picture', str(result))
        self.assertNotIn('x' * 40, str(result))
        self.assertNotIn('camera.test', str(result))

    def test_battery_camera_metadata_requests_on_demand_display(self):
        self.ha.entries['cameras'][0]['onDemand'] = True
        result = self.ha.home()
        self.assertTrue(result['cameras'][0]['onDemand'])
        self.assertNotIn('camera.test', str(result))
