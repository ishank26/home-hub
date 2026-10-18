"""Optional official Govee cloud lights. Credentials and device IDs stay server-only."""
import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from integrations import NoRedirect, SourceUnavailable, private_json


class GoveeCloud:
    def __init__(self, entries, key):
        if not isinstance(entries, list) or not 0 < len(entries) <= 4:
            raise ValueError('Select one to four Govee lights')
        for e in entries:
            if (not isinstance(e, dict) or not re.fullmatch(r'H[0-9A-Z]{4}', e.get('sku', ''))
                    or not re.fullmatch(r'[0-9A-Fa-f:]{16,64}', e.get('device', ''))):
                raise ValueError('Invalid Govee light selection')
        if not isinstance(key, str) or (key and not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key)):
            raise ValueError('Invalid Govee key format')
        self.entries, self.key = entries, key
        self.transport = build_opener(ProxyHandler({}), NoRedirect())
        self.lock = threading.Lock()
        self.controls = {self.alias(e): threading.Lock() for e in entries}
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='govee')
        self.jobs, self.cache, self.job_versions = {}, {}, {}
        self.versions = {self.alias(e): 0 for e in entries}
        self.control_after = {self.alias(e): 0 for e in entries}
        self.backoff_until = 0
        self.health = {'state': 'failed', 'updatedAt': None}

    @staticmethod
    def alias(entry):
        return 'g' + hashlib.sha256((entry['sku'] + ':' + entry['device']).encode()).hexdigest()[:16]

    def request(self, endpoint, payload=None):
        if time.monotonic() < self.backoff_until:
            raise SourceUnavailable('Govee cloud is cooling down; retry later')
        if endpoint not in ('user/devices', 'device/state', 'device/control') or not self.key:
            raise SourceUnavailable('Govee needs local setup')
        data = None if payload is None else json.dumps({'requestId': str(uuid.uuid4()), 'payload': payload}).encode()
        req = Request('https://openapi.api.govee.com/router/api/v1/' + endpoint, data=data,
                      headers={'Govee-API-Key': self.key, 'Content-Type': 'application/json'})
        try:
            with self.transport.open(req, timeout=2) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError('Response too large')
                value = json.loads(raw)
            if not isinstance(value, dict) or value.get('code') != 200:
                raise ValueError('Provider rejected request')
            return value
        except HTTPError as error:
            if error.code == 429:
                self.backoff_until = time.monotonic() + 60
            raise SourceUnavailable('Govee cloud unavailable; check local setup or retry later') from None
        except (URLError, OSError, ValueError):
            raise SourceUnavailable('Govee cloud unavailable; check local setup or retry later') from None

    def read(self, entry):
        result = self.request('device/state', {'sku': entry['sku'], 'device': entry['device']})
        payload = result.get('payload', {})
        if not isinstance(payload, dict) or payload.get('sku') != entry['sku'] or payload.get('device') != entry['device']:
            raise SourceUnavailable('Govee state is unconfirmed')
        caps = payload.get('capabilities')
        if not isinstance(caps, list) or len(caps) > 100:
            raise SourceUnavailable('Govee state is unconfirmed')
        values = {}
        for c in caps:
            if (isinstance(c, dict) and isinstance(c.get('state'), dict)
                    and isinstance(c.get('type'), str) and isinstance(c.get('instance'), str)):
                values[(c.get('type'), c.get('instance'))] = c['state'].get('value')
        online = values.get(('devices.capabilities.online', 'online'))
        power = values.get(('devices.capabilities.on_off', 'powerSwitch'))
        available = online is True and type(power) is int and power in (0, 1)
        value = {'id': self.alias(entry), 'name': entry.get('name', 'Govee light'), 'on': available and power == 1,
                 'available': available, 'detail': 'Govee cloud' if available else 'Govee unavailable'}
        brightness = values.get(('devices.capabilities.range', 'brightness'))
        if available and type(brightness) is int and 0 <= brightness <= 100:
            value['brightness'] = brightness
        return value

    def lights(self):
        with self.lock:
            now = time.monotonic()
            for e in self.entries:
                alias = self.alias(e)
                if alias not in self.jobs and (alias not in self.cache or now - self.cache[alias][0] >= 60):
                    self.jobs[alias] = self.pool.submit(self.read, e)
                    self.job_versions[alias] = self.versions[alias]
        # Never wait for cloud IO in the Home response. One job per light is
        # reused across requests; failures back off for a minute.
        with self.lock:
            for alias, job in list(self.jobs.items()):
                if not job.done():
                    continue
                try:
                    value = job.result()
                except Exception:
                    value = None
                if self.job_versions.pop(alias) == self.versions[alias]:
                    self.cache[alias] = (time.monotonic(), value)
                    if value is not None and value['available']:
                        self.health['updatedAt'] = datetime.now().astimezone().isoformat()
                del self.jobs[alias]
            result = []
            for e in self.entries:
                fetched, value = self.cache.get(self.alias(e), (0, None))
                if time.monotonic() - fetched >= 60:
                    value = None
                result.append(value if value is not None else {'id': self.alias(e), 'name': e.get('name', 'Govee light'),
                              'on': False, 'available': False, 'detail': 'Govee unavailable'})
            self.health['state'] = 'current' if all(e['available'] for e in result) else 'failed'
            return result

    def action(self, body):
        entry = next((e for e in self.entries if self.alias(e) == body.get('id')), None)
        if entry is None or body.get('kind') != 'light' or type(body.get('on')) is not bool:
            raise ValueError('Unsupported Govee action')
        alias = self.alias(entry)
        if not self.controls[alias].acquire(blocking=False):
            raise SourceUnavailable('Govee light is busy')
        if time.monotonic() < self.control_after[alias]:
            self.controls[alias].release()
            raise SourceUnavailable('Govee light is cooling down; retry later')
        self.control_after[alias] = time.monotonic() + 2
        confirmed = None
        try:
            if not self.read(entry)['available']:
                raise SourceUnavailable('Govee light is unavailable')
            self.request('device/control', {'sku': entry['sku'], 'device': entry['device'], 'capability': {
                'type': 'devices.capabilities.on_off', 'instance': 'powerSwitch', 'value': int(body['on'])}})
            state = self.read(entry)
            if not state['available'] or state['on'] != body['on']:
                raise SourceUnavailable('Command sent; Govee state is not yet confirmed')
            confirmed = state
            return {'result': 'confirmed', 'message': entry.get('name', 'Govee light') + (' on' if body['on'] else ' off')}
        finally:
            with self.lock:
                self.versions[alias] += 1
                self.cache[alias] = (time.monotonic(), confirmed)
            self.controls[alias].release()


def from_config(config):
    settings = config.get('govee')
    if settings is None:
        return None
    from pathlib import Path
    secrets = private_json(Path.home() / '.config/home-hub/secrets.json')
    return GoveeCloud(settings.get('lights', []), secrets.get('govee_api_key', ''))
