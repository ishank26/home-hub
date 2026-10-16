"""Server-only Home Assistant bridge. No HA secrets or arbitrary services reach clients."""
import hashlib
import json
import os
import re
import stat
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo


class SourceUnavailable(Exception):
    pass


def private_json(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Integration configuration must be an owner-only regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Integration configuration must be an object')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HomeAssistant:
    def __init__(self, config, token=''):
        # Preserve this host's loopback-only HA deployment and never follow redirects
        # with its bearer token. Private host/device identifiers stay in config.
        self.url = config.get('url', 'http://127.0.0.1:8123').rstrip('/')
        if self.url != 'http://127.0.0.1:8123':
            raise ValueError('Home Assistant must use the local loopback endpoint')
        self.token = token
        self.zone = ZoneInfo(config.get('timezone', 'America/New_York'))
        self.config = config
        self.cache = {}
        self.health = {}
        self.locks = {'home': threading.RLock(), 'calendar': threading.RLock()}
        self.transport = build_opener(ProxyHandler({}), NoRedirect())
        self.entries = {}
        for kind, domain in [('calendars', 'calendar'), ('lights', 'light'), ('contacts', 'binary_sensor')]:
            entries = config.get(kind, [])
            if not isinstance(entries, list) or len(entries) > 12:
                raise ValueError('At most twelve entities per source')
            for entry in entries:
                if not isinstance(entry, dict) or not re.fullmatch(domain + r'\.[a-z0-9_]+', entry.get('entity', '')):
                    raise ValueError('Invalid allowlisted entity')
            self.entries[kind] = entries

    def request(self, path, body=None):
        if not self.token:
            raise SourceUnavailable('Home Assistant connection needs local setup')
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.url + path, data=data, headers=headers)
        try:
            with self.transport.open(req, timeout=2) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise SourceUnavailable('Home Assistant response too large')
                return json.loads(raw)
        except (HTTPError, URLError, OSError, ValueError) as error:
            # URLs, tokens and upstream bodies must not enter HTTP errors or logs.
            raise SourceUnavailable('Home Assistant is unavailable; check local setup') from None

    @staticmethod
    def alias(entity):
        return hashlib.sha256(entity.encode()).hexdigest()[:16]

    def cached(self, source, key, ttl, load):
        with self.locks[source]:
            old = self.cache.get(key)
            if old and time.monotonic() - old[0] < ttl:
                return old[1]
            try:
                value = load()
            except SourceUnavailable:
                self.health[source] = {'state': 'stale' if old else 'failed',
                                       'updatedAt': old[1]['updatedAt'] if old else None}
                # Let the browser use its last-good cache and label it stale.
                raise
            if len(self.cache) >= 24 and key not in self.cache:
                del self.cache[next(iter(self.cache))]
            self.cache[key] = (time.monotonic(), value)
            self.health[source] = {'state': 'current', 'updatedAt': value['updatedAt']}
            return value

    def calendar(self, start, end):
        entries = self.entries['calendars']
        if not entries or not self.token:
            self.health['calendar'] = {'state': 'failed', 'updatedAt': None}
            return {'source': 'unconfigured', 'updatedAt': None, 'calendars': [], 'events': []}

        def load():
            calendars, events = [], []
            deadline = time.monotonic() + 4
            for i, entry in enumerate(entries):
                if time.monotonic() > deadline:
                    raise SourceUnavailable('Calendar refresh timed out')
                entity = entry['entity']
                cid = self.alias(entity)
                color = entry.get('color', ['blue', 'orange', 'teal', 'purple'][i % 4])
                if color not in ('blue', 'orange', 'teal', 'purple'):
                    color = 'blue'
                calendars.append({'id': cid, 'name': entry.get('name', 'Calendar'), 'color': color})
                params = urlencode({'start': start.isoformat(), 'end': end.isoformat()})
                result = self.request('/api/calendars/' + quote(entity, safe='') + '?' + params)
                if not isinstance(result, list):
                    raise SourceUnavailable('Calendar response unavailable')
                for event in result:
                    try:
                        begin = event['start'].get('dateTime', event['start'].get('date'))
                        finish = event['end'].get('dateTime', event['end'].get('date'))
                        all_day = 'date' in event['start']
                        begin_dt = datetime.fromisoformat(begin)
                        end_dt = datetime.fromisoformat(finish)
                        if begin_dt.tzinfo is None:
                            begin_dt = begin_dt.replace(tzinfo=self.zone)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=self.zone)
                        begin_dt = begin_dt.astimezone(self.zone)
                        end_dt = end_dt.astimezone(self.zone)
                        if end_dt <= start or begin_dt >= end:
                            continue
                        events.append({'id': self.alias(entity + str(event.get('uid', '')) + begin),
                                       'title': event.get('summary', 'Untitled event'), 'calendar': cid,
                                       'location': event.get('location', ''), 'allDay': all_day,
                                       'start': begin_dt.isoformat(), 'end': end_dt.isoformat()})
                    except (KeyError, TypeError, ValueError, AttributeError):
                        raise SourceUnavailable('Calendar event could not be read') from None
            events.sort(key=lambda e: datetime.fromisoformat(e['start']))
            return {'source': 'homeassistant', 'updatedAt': datetime.now().astimezone().isoformat(),
                    'calendars': calendars, 'events': events}
        return self.cached('calendar', ('calendar', start.isoformat(), end.isoformat()), 300, load)

    def home(self):
        if not self.token or not any(self.entries[k] for k in ('lights', 'contacts')):
            self.health['home'] = {'state': 'failed', 'updatedAt': None}
            return {'source': 'unconfigured', 'updatedAt': None, 'contacts': [], 'lights': [], 'scenes': [],
                    'cameras': [], 'doorbell': {'name': 'Doorbell', 'verified': False},
                    'hub': {'name': 'Add devices in Home Assistant', 'online': False}, 'alerts': []}

        def load():
            lights, contacts = [], []
            deadline = time.monotonic() + 4
            for kind in ('lights', 'contacts'):
                for entry in self.entries[kind]:
                    if time.monotonic() > deadline:
                        raise SourceUnavailable('Home Assistant refresh timed out')
                    entity = entry['entity']
                    result = self.read_state(entity)
                    state = result.get('state')
                    available = state in ('on', 'off')
                    attrs = result.get('attributes', {})
                    item = {'id': self.alias(entity), 'name': entry.get('name', attrs.get('friendly_name', kind)),
                            'available': available}
                    if kind == 'lights':
                        item.update(on=state == 'on', detail='Home Assistant' if available else 'Unavailable')
                        if available and isinstance(attrs.get('brightness'), (int, float)):
                            item['brightness'] = round(attrs['brightness'] / 255 * 100)
                        lights.append(item)
                    else:
                        item['open'] = state == 'on' if available else None
                        contacts.append(item)
            return {'source': 'homeassistant', 'updatedAt': datetime.now().astimezone().isoformat(),
                    'contacts': contacts, 'lights': lights, 'scenes': [], 'cameras': [], 'alerts': [],
                    'doorbell': {'name': 'Doorbell', 'verified': False},
                    'hub': {'name': 'Home Assistant', 'online': True}}
        return self.cached('home', 'home', 15, load)

    def read_state(self, entity):
        result = self.request('/api/states/' + quote(entity, safe=''))
        if not isinstance(result, dict) or not isinstance(result.get('state'), str):
            raise SourceUnavailable('Device state is unavailable')
        if not isinstance(result.get('attributes', {}), dict):
            raise SourceUnavailable('Device attributes are unavailable')
        return result

    def action(self, body):
        if body.get('kind') != 'light' or type(body.get('on')) is not bool:
            raise ValueError('Unsupported device action')
        entry = next((e for e in self.entries['lights'] if self.alias(e['entity']) == body.get('id')), None)
        if entry is None:
            raise ValueError('Unknown light')
        with self.locks['home']:
            current = self.read_state(entry['entity'])
            if current.get('state') not in ('on', 'off'):
                raise SourceUnavailable('Light is unavailable')
            try:
                target = 'on' if body['on'] else 'off'
                self.request('/api/services/light/turn_' + target, {'entity_id': entry['entity']})
                confirmed = self.read_state(entry['entity'])
                if confirmed.get('state') != target:
                    raise SourceUnavailable('Command sent; device state is not yet confirmed')
                return {'result': 'confirmed', 'message': entry.get('name', 'Light') + ' ' + target}
            finally:
                self.cache.pop('home', None)


def from_config(config):
    if 'homeassistant' not in config:
        return None
    secrets_file = Path.home() / '.config/home-hub/secrets.json'
    secret = private_json(secrets_file) if secrets_file.exists() else {}
    token = secret.get('homeassistant_token', '')
    if not isinstance(token, str):
        raise ValueError('Invalid Home Assistant credential')
    return HomeAssistant(config['homeassistant'], token)
