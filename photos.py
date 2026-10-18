"""Serve only published, normalized photo copies. No cloud identifiers or URLs."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from integrations import SourceUnavailable

PHOTO_ID = re.compile(r'[a-f0-9]{32}')
MAX_PHOTOS = 1000


class PhotoLibrary:
    def __init__(self, directory, enabled=False):
        self.directory = Path(directory)
        self.enabled = enabled

    def manifest(self):
        try:
            path = self.directory / 'manifest.json'
            if path.stat().st_size > 512_000 or path.is_symlink():
                raise ValueError('manifest size')
            value = json.loads(path.read_text())
            photos = value['photos']
            stamp = datetime.fromisoformat(value['syncedAt'])
            if stamp.tzinfo is None or not isinstance(photos, list) or len(photos) > MAX_PHOTOS:
                raise ValueError('manifest shape')
            if any(not isinstance(p, dict) or not PHOTO_ID.fullmatch(p.get('id', '')) for p in photos):
                raise ValueError('photo id')
            max_age = 4500 if value.get('sampling') == 'hourly-random' else 1800
            stale = (datetime.now(timezone.utc) - stamp).total_seconds() > max_age
            try:
                status_path = self.directory / 'status.json'
                if status_path.is_symlink() or status_path.stat().st_size > 16_000:
                    raise ValueError('status size')
                status = json.loads(status_path.read_text())
                stale = stale or not isinstance(status, dict) or status.get('state') != 'current'
            except (OSError, ValueError):
                stale = True
            return {'source': 'aura', 'state': 'stale' if stale else 'current',
                    'syncedAt': stamp.isoformat(), 'windowLimited': value.get('windowLimited') is True,
                    'syncPending': value.get('syncPending') is True,
                    'sampling': 'hourly-random' if value.get('sampling') == 'hourly-random' else None, 'collections': ['All', 'Aura'],
                    'photos': [{'id': p['id'], 'collections': ['All', 'Aura']} for p in photos]}
        except FileNotFoundError:
            return {'source': 'unconfigured', 'state': 'failed', 'syncedAt': None,
                    'collections': ['All', 'Aura'], 'photos': []}
        except (OSError, ValueError, KeyError, TypeError):
            raise SourceUnavailable('Photo cache unavailable; retry after the next sync') from None

    def status(self):
        try:
            manifest = self.manifest()
            return {'state': manifest['state'], 'updatedAt': manifest['syncedAt']}
        except SourceUnavailable:
            return {'state': 'failed', 'updatedAt': None}

    def read(self, photo_id, thumbnail=False):
        if not PHOTO_ID.fullmatch(photo_id):
            raise FileNotFoundError
        if photo_id not in {p['id'] for p in self.manifest()['photos']}:
            raise FileNotFoundError
        path = self.directory / 'cache' / (photo_id + ('.thumb.jpg' if thumbnail else '.jpg'))
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
            raise FileNotFoundError
        try:
            return path.read_bytes()
        except OSError:
            raise FileNotFoundError from None
