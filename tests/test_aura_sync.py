"""Synthetic Aura contract/image tests. No real accounts, downloads or photos."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from aura_sync import AuraClient, AuraError, atomic_json, normalize, synchronize
from photos import PhotoLibrary
from integrations import SourceUnavailable


class ClientTests(unittest.TestCase):
    def test_login_session_does_not_retain_password(self):
        client = AuraClient()
        response = {'result': {'current_user': {'id': 'synthetic-user', 'auth_token': 'synthetic-token'}}}
        with patch.object(client, '_fetch', return_value=json.dumps(response).encode()) as fetch:
            session = client.login('owner@example.test', 'synthetic-password')
        self.assertEqual(session['user_id'], 'synthetic-user')
        self.assertNotIn('synthetic-password', str(vars(client)))
        self.assertEqual(fetch.call_args.kwargs['data']['user']['email'], 'owner@example.test')
        self.assertFalse(fetch.call_args.kwargs['authenticate'])

    def test_closed_api_operation_set(self):
        client = AuraClient()
        for route in ['/assets/destroy.json', '/account/delete', '/frames/f1/remove_asset.json']:
            with self.assertRaises(AuraError):
                client._api(route)
        with self.assertRaises(AuraError):
            client._api('/frames.json', data={'name': 'change'})

    def test_api_token_never_sent_to_image_host(self):
        client = AuraClient({'user_id': 'test-user', 'auth_token': 'test-token'})
        with patch.object(client.http, 'open', return_value=io.BytesIO(b'photo')) as opened:
            client.image({'user_id': 'u1', 'file_name': 'image.jpg'})
            request = opened.call_args.args[0]
            self.assertEqual(request.host, 'imgproxy.pushd.com')
            self.assertFalse(any('token' in k.lower() or 'user-id' in k.lower() for k in request.headers))
        for url in ['http://imgproxy.pushd.com/x', 'https://127.0.0.1/private',
                    'https://imgproxy.pushd.com.evil.test/x', 'https://imgproxy.pushd.com:444/x']:
            with self.assertRaises(AuraError):
                client._fetch(url)

    def test_pagination_deduplicates_and_skips_videos_hidden_assets(self):
        client = AuraClient()
        pages = [
            {'assets': [{'id': 'a1'}, {'id': 'hidden', 'hidden': True}, {'id': 'video', 'video_file_name': 'v'}],
             'next_page_cursor': 'next'},
            {'assets': [{'id': 'a1'}, {'id': 'a2', 'is_live': True, 'video_file_name': 'motion'}]}]
        with patch.object(client, '_api', side_effect=pages):
            self.assertEqual([a['id'] for a in client.assets('frame-1')], ['a1', 'a2'])
        with patch.object(client, '_api', return_value={'assets': [], 'next_page_cursor': 'loop'}):
            with self.assertRaisesRegex(AuraError, 'pagination'):
                client.assets('frame-1')

    def test_transport_does_not_inherit_proxies_and_rejects_redirects(self):
        with patch.dict(os.environ, {'https_proxy': 'https://example.test:8443'}):
            client = AuraClient()
        self.assertFalse(any(getattr(h, 'proxies', {}) for h in client.http.handlers))
        redirect = next(h for h in client.http.handlers if hasattr(h, 'redirect_request'))
        self.assertIsNone(redirect.redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_download_limit_and_malformed_response(self):
        client = AuraClient()
        with patch.object(client.http, 'open', return_value=io.BytesIO(b'12345')):
            with self.assertRaisesRegex(AuraError, 'limit'):
                client._fetch('https://imgproxy.pushd.com/photo', limit=4)
        with patch.object(client, '_fetch', return_value=b'not-json'):
            with self.assertRaises(AuraError):
                client._api('/frames.json')


class LibraryTests(unittest.TestCase):
    def test_missing_library_is_unconfigured(self):
        with tempfile.TemporaryDirectory() as directory:
            library = PhotoLibrary(directory, enabled=True)
            self.assertEqual(library.manifest()['source'], 'unconfigured')
            self.assertEqual(library.manifest()['photos'], [])

    def test_only_published_ids_are_served_and_stale_age_is_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'cache').mkdir()
            pid = 'a' * 32
            atomic_json(root / 'manifest.json', {'photos': [{'id': pid}],
                        'syncedAt': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
            atomic_json(root / 'status.json', {'state': 'current'})
            (root / 'cache' / (pid + '.jpg')).write_bytes(b'JPEG')
            library = PhotoLibrary(root, enabled=True)
            self.assertEqual(library.manifest()['state'], 'stale')
            self.assertEqual(library.read(pid), b'JPEG')
            for invalid in ['../secret', 'b' * 32, pid + '.jpg']:
                with self.assertRaises(FileNotFoundError):
                    library.read(invalid)
            (root / 'cache' / (pid + '.jpg')).unlink()
            (root / 'cache' / (pid + '.jpg')).symlink_to(root / 'status.json')
            with self.assertRaises(FileNotFoundError):
                library.read(pid)

    def test_malformed_manifest_never_leaks_its_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_json(root / 'manifest.json', {'photos': [{'id': '../../private'}], 'syncedAt': 'bad'})
            with self.assertRaisesRegex(SourceUnavailable, '^Photo cache unavailable'):
                PhotoLibrary(root).manifest()

    def test_malformed_status_keeps_last_good_photos_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic_json(root / 'manifest.json', {'photos': [{'id': 'a' * 32}],
                        'syncedAt': datetime.now(timezone.utc).isoformat()})
            for malformed in [[], None, 'bad']:
                atomic_json(root / 'status.json', malformed)
                result = PhotoLibrary(root).manifest()
                self.assertEqual(result['state'], 'stale')
                self.assertEqual(len(result['photos']), 1)


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Run Aura image tests with the installed aura-venv Python')
class ImageSyncTests(unittest.TestCase):
    def image(self):
        from PIL import Image
        image = Image.new('RGB', (1800, 1200), 'blue')
        exif = Image.Exif()
        exif[270] = 'private caption'
        exif[274] = 6
        output = io.BytesIO()
        image.save(output, format='JPEG', exif=exif)
        return output.getvalue()

    def test_resizes_orientation_and_strips_metadata(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            full, thumb = Path(directory) / 'full.jpg', Path(directory) / 'thumb.jpg'
            normalize(self.image(), full)
            normalize(self.image(), thumb, thumbnail=True)
            with Image.open(full) as result:
                self.assertLessEqual(result.width, 1280)
                self.assertLessEqual(result.height, 800)
                self.assertLess(result.width, result.height)
                self.assertFalse(result.getexif())
                self.assertNotIn('xmp', result.info)
            with Image.open(thumb) as result:
                self.assertLessEqual(result.width, 400)
                self.assertLessEqual(result.height, 250)

    def test_atomic_sync_deduplication_failure_and_removal(self):
        client = AuraClient()
        asset = {'id': 'photo-1', 'file_name': 'remote-private-name.jpg', 'user_id': 'user-1',
                 'location': [40, -74], 'original_file_name': 'private-name.jpg'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(client, 'assets', return_value=[asset]), patch.object(client, 'image', return_value=self.image()) as download:
                self.assertEqual(synchronize(client, 'frame-1', root), 1)
                self.assertEqual(synchronize(client, 'frame-1', root), 1)
                self.assertEqual(download.call_count, 1)
            original = (root / 'manifest.json').read_bytes()
            manifest = PhotoLibrary(root).manifest()
            self.assertEqual(manifest['source'], 'aura')
            self.assertNotIn('remote-private', str(manifest))
            self.assertNotIn('location', str(manifest))
            changed = {**asset, 'id': 'photo-2'}
            with patch.object(client, 'assets', return_value=[asset, changed]), patch.object(client, 'image', side_effect=AuraError('offline')):
                with self.assertRaises(AuraError):
                    synchronize(client, 'frame-1', root)
            self.assertEqual((root / 'manifest.json').read_bytes(), original)
            self.assertEqual(PhotoLibrary(root).manifest()['state'], 'stale')
            with patch.object(client, 'assets', return_value=[]):
                synchronize(client, 'frame-1', root)
            self.assertEqual(PhotoLibrary(root).manifest()['photos'], [])

    def test_corrupt_image_preserves_old_manifest(self):
        client = AuraClient()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(client, 'assets', return_value=[]):
                synchronize(client, 'frame-1', root)
            before = (root / 'manifest.json').read_bytes()
            with patch.object(client, 'assets', return_value=[{'id': 'broken'}]), patch.object(client, 'image', return_value=b'not-an-image'):
                with self.assertRaises(AuraError):
                    synchronize(client, 'frame-1', root)
            self.assertEqual((root / 'manifest.json').read_bytes(), before)

    def test_failed_sync_rolls_back_unpublished_downloads_and_respects_budget(self):
        client = AuraClient()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(client, 'assets', return_value=[]):
                synchronize(client, 'frame-1', root)
            for attempt in range(3):
                with patch.object(client, 'assets', return_value=[{'id': f'a{attempt}'}, {'id': 'broken'}]), patch.object(client, 'image', side_effect=[self.image(), AuraError('offline')]):
                    with self.assertRaises(AuraError):
                        synchronize(client, 'frame-1', root)
                self.assertEqual(list((root / 'cache').iterdir()), [])
            with patch.object(client, 'assets', return_value=[{'id': 'a'}]), patch('aura_sync.MAX_CACHE_BYTES', 1):
                with self.assertRaisesRegex(AuraError, 'budget'):
                    synchronize(client, 'frame-1', root)

    def test_interruption_after_publication_preserves_referenced_images(self):
        client = AuraClient()
        def interrupted_write(path, value):
            atomic_json(path, value)
            if path.name == 'manifest.json':
                raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(client, 'assets', return_value=[{'id': 'a'}]), patch.object(client, 'image', return_value=self.image()), patch('aura_sync.atomic_json', side_effect=interrupted_write):
                with self.assertRaises(KeyboardInterrupt):
                    synchronize(client, 'frame-1', root)
            library = PhotoLibrary(root)
            pid = library.manifest()['photos'][0]['id']
            self.assertGreater(len(library.read(pid)), 100)
