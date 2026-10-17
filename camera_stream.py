"""One bounded HLS viewer. Home Assistant stream credentials never reach clients."""
import json
from contextlib import closing
import re
import secrets
import socket
import threading
import time
import zlib
from urllib.error import HTTPError, URLError
from urllib.request import Request
from integrations import CameraInactive, SourceUnavailable

RESOURCE = re.compile(r'(?:master_playlist\.m3u8|playlist\.m3u8|init\.mp4|segment/[0-9]{1,12}(?:\.[0-9]{1,6})?\.m4s)')
PREFIX = re.compile(r'/api/hls/[a-f0-9]{16,128}/master_playlist\.m3u8')
# Only HA's known, unencrypted fMP4 HLS vocabulary is accepted.
TAGS = {'EXTM3U','EXT-X-VERSION','EXT-X-STREAM-INF','EXT-X-INDEPENDENT-SEGMENTS',
        'EXT-X-MAP','EXT-X-TARGETDURATION','EXT-X-MEDIA-SEQUENCE','EXT-X-DISCONTINUITY-SEQUENCE',
        'EXT-X-PART-INF','EXT-X-SERVER-CONTROL','EXT-X-START','EXT-X-PART','EXT-X-PRELOAD-HINT',
        'EXT-X-DISCONTINUITY','EXTINF','EXT-X-PROGRAM-DATE-TIME','EXT-X-ENDLIST','EXT-X-GAP'}


def stream_url(ha, entity):
    # Lazy dependency: ordinary stdlib dashboard still runs without video runtime.
    try:
        import websocket
        # A preconnected socket bypasses all websocket-client proxy discovery.
        with closing(socket.create_connection(('127.0.0.1', 8123), timeout=6)) as direct, closing(
                websocket.create_connection('ws://127.0.0.1:8123/api/websocket', timeout=6,
                                            socket=direct, redirect_limit=0, suppress_origin=True)) as ws:
            deadline = time.monotonic() + 6
            def receive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Stream start timeout')
                ws.settimeout(remaining)
                raw = ws.recv()
                if not isinstance(raw, str) or len(raw) > 65536:
                    raise ValueError('Invalid websocket response')
                return json.loads(raw)
            if receive().get('type') != 'auth_required':
                raise ValueError('Unexpected websocket handshake')
            ws.send(json.dumps({'type': 'auth', 'access_token': ha.token}))
            if receive().get('type') != 'auth_ok':
                raise ValueError('Authentication failed')
            ws.send(json.dumps({'id': 1, 'type': 'camera/stream', 'entity_id': entity, 'format': 'hls'}))
            result = receive()
            if result.get('id') != 1 or result.get('success') is not True:
                raise ValueError('Stream start failed')
            url = result['result']['url']
            if not isinstance(url, str) or not PREFIX.fullmatch(url):
                raise ValueError('Invalid stream endpoint')
            return url.rsplit('/', 1)[0] + '/'
    except Exception:
        # Never propagate library exceptions, URLs, provider bodies or tokens.
        raise SourceUnavailable('Live camera could not start; check the streaming runtime and Home Assistant') from None


def rewrite_manifest(raw, session):
    text = raw.decode('utf-8')
    if not text.startswith('#EXTM3U\n') or len(raw) > 65536:
        raise ValueError('Invalid playlist')
    def mapped(value):
        if value.startswith('./'):
            value = value[2:]
        if not RESOURCE.fullmatch(value):
            raise ValueError('Unsupported playlist resource')
        return '/camera/live/' + session + '/' + value
    lines = []
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith('#'):
            tag = line[1:].split(':', 1)[0]
            if tag not in TAGS:
                raise ValueError('Unsupported playlist tag')
            # HA does not use keys, external hosts, variable expansion or redirects.
            line = re.sub(r'URI="([^"]*)"', lambda m: 'URI="' + mapped(m[1]) + '"', line)
            if re.search(r'URI\s*=', re.sub(r'URI="[^"]*"', '', line)):
                raise ValueError('Invalid URI attribute')
            # Fail closed on any otherwise embedded URL or variable.
            if '://' in line or '${' in line:
                raise ValueError('Unsupported playlist value')
            # Use complete segments and ordinary reloads on the legacy frame.
            if tag not in {'EXT-X-PART-INF', 'EXT-X-SERVER-CONTROL', 'EXT-X-START', 'EXT-X-PART', 'EXT-X-PRELOAD-HINT'}:
                lines.append(line)
        else:
            lines.append(mapped(line))
    return ('\n'.join(lines) + '\n').encode()


class LiveCamera:
    def __init__(self, ha):
        self.ha = ha
        self.lock = threading.Lock()
        self.readers = threading.BoundedSemaphore(2)
        self.session = None

    def active(self, entity):
        if self.ha.read_state(entity)['state'] not in ('idle', 'streaming', 'recording'):
            raise CameraInactive('Camera unavailable')

    def start(self, alias):
        entity = next((e['entity'] for e in self.ha.entries['cameras'] if self.ha.alias(e['entity']) == alias), None)
        if entity is None:
            raise ValueError('Unknown camera')
        # One session globally. Starting a viewer revokes the previous viewer.
        if not self.lock.acquire(blocking=False):
            raise SourceUnavailable('Live camera is busy')
        try:
            self.session = None
            self.active(entity)
            upstream = stream_url(self.ha, entity)
            sid = secrets.token_hex(16)
            now = time.monotonic()
            self.session = {'id': sid, 'entity': entity, 'prefix': upstream, 'created': now, 'used': now}
            return {'url': '/camera/live/' + sid + '/master_playlist.m3u8'}
        finally:
            self.lock.release()

    def stop(self, sid):
        with self.lock:
            if self.session and self.session['id'] == sid:
                self.session = None
        return {'stopped': True}

    def resource(self, sid, name):
        if not RESOURCE.fullmatch(name):
            raise ValueError('Invalid live resource')
        if not self.readers.acquire(blocking=False):
            raise SourceUnavailable('Live camera is busy')
        try:
            with self.lock:
                s = self.session
                now = time.monotonic()
                if not s or s['id'] != sid or now - s['used'] > 45 or now - s['created'] > 900:
                    if s and s['id'] == sid:
                        self.session = None
                    raise CameraInactive('Live viewer expired; reopen camera')
            try:
                self.active(s['entity'])
                req = Request(self.ha.url + s['prefix'] + name, headers={'Authorization': 'Bearer ' + self.ha.token, 'Accept-Encoding': 'identity'})
                limit = 65536 if name.endswith('.m3u8') else 8_000_000
                with self.ha.transport.open(req, timeout=6) as response:
                    raw = response.read(limit + 1)
                    if len(raw) > limit:
                        raise ValueError('Live resource too large')
                    encoding = response.headers.get('Content-Encoding', 'identity')
                    if encoding == 'gzip':
                        decoder = zlib.decompressobj(31)
                        raw = decoder.decompress(raw, limit + 1)
                        if len(raw) > limit or not decoder.eof or decoder.unused_data:
                            raise ValueError('Invalid compressed resource')
                    elif encoding != 'identity':
                        raise ValueError('Unsupported content encoding')
                # Check privacy and session again after potentially slow upstream reads.
                self.active(s['entity'])
                with self.lock:
                    if self.session is not s:
                        raise CameraInactive('Live viewer ended')
                    s['used'] = time.monotonic()
                if name.endswith('.m3u8'):
                    return rewrite_manifest(raw, sid), 'application/vnd.apple.mpegurl'
                return raw, 'video/mp4' if name == 'init.mp4' else 'video/iso.segment'
            except CameraInactive:
                self.stop(sid)
                raise
            except HTTPError as error:
                if error.code in (401, 403, 410):
                    self.stop(sid)
                    raise CameraInactive('Camera unavailable') from None
                raise SourceUnavailable('Live camera resource unavailable') from None
            except (URLError, OSError, ValueError, zlib.error):
                raise SourceUnavailable('Live camera resource unavailable') from None
        finally:
            self.readers.release()
