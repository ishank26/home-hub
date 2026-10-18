#!/usr/bin/env python3
"""Minimal read-only Aura client and transactional photo mirror.

Only POST is authentication. Only GET operations list frames/assets or download
their imagery. No uploads, frame controls, cloud deletion or remote metadata edits.
No third-party client code is imported. See docs/aura-protocol.md for evidence.
"""
import argparse
import fcntl
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from integrations import private_json
from photos import MAX_PHOTOS, PHOTO_ID

API = 'https://api.pushd.com/v5'
IMAGE_HOST = 'imgproxy.pushd.com'
CONFIG = Path.home() / '.config/home-hub'
DEFAULT_DATA = Path.home() / '.local/share/home-hub/data'
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_CACHE_BYTES = 512 * 1024 * 1024
MAX_CACHE_FILES = 4000
MAX_NEW_PHOTOS = 100  # Publish a useful first batch, then fill the window on later syncs.
MIN_FREE_BYTES = 128 * 1024 * 1024


class AuraError(Exception):
    """Safe user-facing error: never includes a request, URL, token or body."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
        raise AuraError('Aura returned an unsupported identifier')
    return value


class AuraClient:
    def __init__(self, session=None):
        self.session = session or {}
        # Neither account tokens nor image requests inherit proxy environment.
        self.http = build_opener(ProxyHandler({}), NoRedirect())

    def _fetch(self, url, data=None, authenticate=False, limit=2_000_000):
        expected = 'api.pushd.com' if authenticate or data is not None else IMAGE_HOST
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == 'https' and parsed.hostname == expected
                     and parsed.port in (None, 443) and not parsed.username)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise AuraError('Untrusted Aura endpoint refused')
        headers = {'User-Agent': 'HomeHub-AuraMirror/1.0', 'Accept': 'application/json' if expected == 'api.pushd.com' else 'image/*'}
        if authenticate:
            token = self.session.get('auth_token')
            if not isinstance(token, str) or not token or any(ord(c) < 32 for c in token):
                raise AuraError('Aura sign-in is required')
            headers.update({'X-User-Id': identifier(self.session.get('user_id')), 'X-Token-Auth': token})
        raw = json.dumps(data).encode() if data is not None else None
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(url, data=raw, headers=headers)
        try:
            with self.http.open(request, timeout=20) as response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise AuraError('Aura response exceeded the download limit')
                return body
        except HTTPError as error:
            if error.code in (401, 403):
                raise AuraError('Aura access denied; sign in again locally') from None
            if error.code == 429:
                raise AuraError('Aura rate limit reached; sync will retry later') from None
            raise AuraError('Aura service request failed') from None
        except (OSError, URLError, ValueError):
            raise AuraError('Aura could not be reached securely') from None

    def _api(self, path, query=None, data=None):
        # Closed operation set: keep accidental destructive requests impossible.
        if path not in ('/login.json', '/frames.json') and not re.fullmatch(r'/frames/[A-Za-z0-9_-]+/assets\.json', path):
            raise AuraError('Unsupported Aura operation')
        if data is not None and path != '/login.json':
            raise AuraError('Aura writes are not supported')
        url = API + path + ('?' + urlencode(query) if query else '')
        try:
            result = json.loads(self._fetch(url, data=data, authenticate=path != '/login.json'))
            if not isinstance(result, dict) or result.get('error'):
                raise AuraError('Aura rejected the request')
            return result
        except (ValueError, TypeError):
            raise AuraError('Aura returned an unsupported response') from None

    def login(self, email, password):
        device = str(uuid.uuid4())
        result = self._api('/login.json', data={
            'user': {'email': email, 'password': password}, 'locale': 'en-US',
            'app_identifier': 'com.pushd.Framelord',
            'identifier_for_vendor': device, 'client_device_id': device})
        try:
            user = result['result']['current_user']
            token = user['auth_token']
            if not isinstance(token, str) or not token or len(token) > 8192 or any(ord(c) < 32 for c in token):
                raise ValueError
            self.session = {'user_id': identifier(user['id']), 'auth_token': token, 'device_id': device}
            return self.session
        except (KeyError, TypeError, ValueError):
            raise AuraError('Aura login did not return a usable session; check your account locally') from None

    def frames(self):
        frames = self._api('/frames.json').get('frames')
        if not isinstance(frames, list) or len(frames) > 100:
            raise AuraError('Aura frame list is unavailable')
        return [{'id': identifier(f['id']), 'name': re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(f.get('name', 'Aura frame')))[:100]}
                for f in frames if isinstance(f, dict) and 'id' in f]

    def assets(self, frame_id):
        frame_id = identifier(frame_id)
        found, cursors, cursor = {}, set(), None
        self.window_limited = False
        for _ in range(100):
            query = {'limit': 100}
            if cursor is not None:
                query['cursor'] = cursor
            page = self._api('/frames/' + frame_id + '/assets.json', query=query)
            assets = page.get('assets')
            if not isinstance(assets, list) or len(assets) > 1000:
                raise AuraError('Aura asset list is unavailable')
            for index, asset in enumerate(assets):
                if not isinstance(asset, dict):
                    raise AuraError('Aura asset response is malformed')
                aid = identifier(asset.get('id'))
                if asset.get('hidden') is True or asset.get('selected') is False:
                    continue
                if asset.get('video_file_name') and not asset.get('is_live'):
                    continue  # Live Photos use their still image; videos are excluded.
                found[aid] = asset
                if len(found) == MAX_PHOTOS:
                    # Keep the existing disk/memory bounds for large frames.
                    # Vendor order is preserved; no assumption about recency.
                    self.window_limited = index < len(assets) - 1 or bool(page.get('next_page_cursor'))
                    return list(found.values())
            cursor = page.get('next_page_cursor')
            if not cursor:
                return list(found.values())
            if not isinstance(cursor, str) or len(cursor) > 4096 or cursor in cursors:
                raise AuraError('Aura pagination did not progress')
            cursors.add(cursor)
        raise AuraError('Aura pagination exceeded the page limit')

    def image(self, asset):
        # Use Aura's landscape rendering when present, otherwise its documented
        # image-proxy path. Never send API credentials to an image host.
        url = asset.get('landscape_16_10_url') or asset.get('landscape_url')
        try:
            known_proxy = isinstance(url, str) and urlsplit(url).hostname == IMAGE_HOST
        except ValueError:
            known_proxy = False
        if not known_proxy:
            filename = asset.get('file_name')
            if not isinstance(filename, str) or not 1 <= len(filename) <= 512:
                raise AuraError('Aura photo has no supported image path')
            url = 'https://' + IMAGE_HOST + '/' + identifier(asset.get('user_id')) + '/' + quote(filename, safe='')
        return self._fetch(url, limit=MAX_IMAGE_BYTES)


def normalize(raw, destination, thumbnail=False):
    # Pillow is needed by this separate worker only, never the dashboard server.
    from PIL import Image, ImageOps, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = 25_000_000
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in ('JPEG', 'PNG', 'WEBP', 'GIF'):
                    raise AuraError('Unsupported Aura image format')
                original.seek(0)
                image = ImageOps.exif_transpose(original)
                image.thumbnail((400, 250) if thumbnail else (1280, 800), Image.Resampling.LANCZOS)
                # A new image deliberately drops EXIF, GPS, XMP, ICC and comments.
                clean = Image.new('RGB', image.size, '#000000')
                if image.mode in ('RGBA', 'LA') or image.mode == 'P' and 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    clean.paste(image.convert('RGB'))
                fd, tmp = tempfile.mkstemp(dir=destination.parent, prefix='.image-')
                try:
                    with os.fdopen(fd, 'wb') as output:
                        clean.save(output, format='JPEG', quality=85, optimize=True)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(tmp, destination)
                finally:
                    Path(tmp).unlink(missing_ok=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AuraError('Aura photo could not be safely decoded') from None


def cache_usage(cache, protected):
    """Prune only old worker outputs; bound traversal and count every cache byte."""
    count, size, scanned = 0, 0, 0
    with os.scandir(cache) as entries:
        for entry in entries:
            scanned += 1
            if scanned > MAX_CACHE_FILES * 2:
                raise AuraError('Aura cache cleanup reached its scan limit')
            if count >= MAX_CACHE_FILES:
                raise AuraError('Aura photo cache file limit reached')
            info = entry.stat(follow_symlinks=False)
            if entry.is_symlink():
                raise AuraError('Unexpected link in Aura cache')
            pid = entry.name.split('.')[0]
            generated = PHOTO_ID.fullmatch(pid) and entry.name in (pid + '.jpg', pid + '.thumb.jpg')
            old = time.time() - info.st_mtime > 86400
            if old and ((generated and pid not in protected) or entry.name.startswith('.image-')):
                if entry.is_file(follow_symlinks=False):
                    Path(entry.path).unlink()
                    continue
            count += 1
            size += info.st_size
            if size > MAX_CACHE_BYTES:
                raise AuraError('Aura photo cache byte limit reached')
    return count, size


def synchronize(client, frame_id, directory):
    """Publish only a complete snapshot. Failures leave the last manifest intact."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache = directory / 'cache'
    cache.mkdir(mode=0o700, exist_ok=True)
    with (directory / '.sync-lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AuraError('A photo sync is already running') from None
        created = []
        published = False
        try:
            try:
                previous = json.loads((directory / 'manifest.json').read_text())
                protected = {p['id'] for p in previous['photos']}
            except FileNotFoundError:
                protected = set()
            except (OSError, ValueError, TypeError, KeyError):
                raise AuraError('Previous photo manifest needs local repair') from None
            file_count, byte_count = cache_usage(cache, protected)
            started = time.monotonic()
            assets = client.assets(frame_id)
            photos, downloaded, pending = [], 0, False
            for asset in assets:
                revision = '|'.join(str(asset.get(k, '')) for k in ('id', 'file_name', 'md5_hash', 'modified_at', 'rotation_cw'))
                pid = hashlib.sha256((frame_id + ':' + revision).encode()).hexdigest()[:32]
                display, thumb = cache / (pid + '.jpg'), cache / (pid + '.thumb.jpg')
                if not display.is_file() or not thumb.is_file() or display.is_symlink() or thumb.is_symlink():
                    if downloaded >= MAX_NEW_PHOTOS or time.monotonic() - started > 300:
                        pending = True
                        continue
                    if (file_count + 2 > MAX_CACHE_FILES or byte_count + 8_000_000 > MAX_CACHE_BYTES
                            or shutil.disk_usage(cache).free < MIN_FREE_BYTES + 8_000_000):
                        raise AuraError('Aura photo cache space budget reached')
                    fresh = [path for path in (display, thumb) if not path.exists()]
                    created.extend(fresh)
                    raw = client.image(asset)
                    normalize(raw, display)
                    normalize(raw, thumb, thumbnail=True)
                    downloaded += 1
                    file_count += len(fresh)
                    byte_count += sum(path.stat().st_size for path in fresh)
                photos.append({'id': pid})
            if pending and not photos:
                raise AuraError('Aura sync has no completed photos yet; retry locally')
            stamp = datetime.now(timezone.utc).isoformat()
            atomic_json(directory / 'manifest.json', {'syncedAt': stamp, 'photos': photos,
                         'windowLimited': getattr(client, 'window_limited', False) is True, 'syncPending': pending})
            published = True
            atomic_json(directory / 'status.json', {'state': 'current', 'updatedAt': stamp})
            # Only old generated JPEGs are eligible, after publication and a grace
            # period for an already-running slideshow. No original files are kept.
            cache_usage(cache, {p['id'] for p in photos})
            return len(photos)
        except (AuraError, OSError):
            atomic_json(directory / 'status.json', {'state': 'failed', 'error': 'Aura sync failed; cached photos retained'})
            raise
        finally:
            if not published:
                # Publication may have completed just before an interruption.
                # Read back references rather than deleting possibly-live images.
                try:
                    current = json.loads((directory / 'manifest.json').read_text())
                    live = {p['id'] for p in current['photos']}
                except FileNotFoundError:
                    live = set()
                except (OSError, ValueError, KeyError, TypeError):
                    live = None  # uncertain publication: preserve files, bounded by admission
                for path in created:
                    if live is not None and path.name.split('.')[0] not in live and not path.is_symlink():
                        path.unlink(missing_ok=True)


def setup(config_dir=CONFIG, data=DEFAULT_DATA):
    config_dir = Path(config_dir)
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    print('Sign in to your existing Aura account. Password input is hidden and is not saved.')
    print('This mirror displays up to 1000 eligible photos in Aura API order; larger frames use a bounded selection.')
    email = input('Aura account email: ').strip()
    password = getpass.getpass('Aura password: ')
    client = AuraClient()
    client.login(email, password)
    password = None
    frames = client.frames()
    if not frames:
        raise AuraError('No Aura frame is accessible to this account')
    for index, frame in enumerate(frames, 1):
        # Names are shown only in this owner's local setup terminal, never logs.
        print(f'{index}. {frame["name"]}')
    try:
        selected = int(input('Mirror photos from frame number: ')) - 1
        if selected < 0 or selected >= len(frames):
            raise ValueError
    except ValueError:
        raise AuraError('Invalid frame selection; no configuration saved') from None
    frame_id = frames[selected]['id']
    count = synchronize(client, frame_id, Path(data) / 'photos')
    atomic_json(config_dir / 'aura-session.json', {**client.session, 'frame_id': frame_id})
    path = config_dir / 'config.json'
    config = private_json(path) if path.exists() else {}
    config['photos'] = {'source': 'aura'}
    atomic_json(path, config)
    print(f'Aura connected. Published {count} photos. The Aura password was not saved.')
    print('Large selections fill in batches during automatic sync; the dashboard labels this progress.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup', 'sync'))
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--config-dir', type=Path, default=CONFIG)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'setup':
            setup(args.config_dir, args.data)
        else:
            session = private_json(args.config_dir / 'aura-session.json')
            count = synchronize(AuraClient(session), identifier(session.get('frame_id')), args.data / 'photos')
            print(f'Aura sync completed: {count} photos')
    except AuraError as error:
        print(str(error) + '; cached photos retained.', file=sys.stderr)
        return 1
    except (OSError, ValueError, ImportError):
        # No traceback/raw upstream objects in the journal. Preserve cached data.
        print('Aura sync/setup failed. Check local sign-in, dependencies and connection; cached photos retained.', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('Aura setup cancelled; cached photos retained.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
