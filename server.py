#!/usr/bin/env python3
"""Humblestead Home Hub backend: static UI plus a small JSON API.

Standard library only. Binds 127.0.0.1 by default; pass --host and one or more
--allow addresses to serve the frame on the LAN. LAN clients also need the device
token: the frame opens /pair?token=... once per launch and then carries an HttpOnly
cookie. Loopback clients need no token. Credentials (Home Assistant,
Aura, calendar) belong in adapters on this server and never reach the browser.
Until those adapters exist every response is marked "source": "sample".
"""
import argparse
import copy
import hmac
import ipaddress
import json
import os
import re
import secrets
import stat
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from camera_stream import LiveCamera
from integrations import CameraInactive, SourceUnavailable, from_config, private_json
from photos import PhotoLibrary
from weather import Weather, empty_weather
from shopping import ShoppingBridge

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
DATA = Path(os.environ.get('HOME_HUB_DATA', ROOT / 'data'))
CATEGORIES = ('Produce', 'Dairy', 'Pantry', 'Household', 'Other')
MAX_BODY = 16384
TOKEN_COOKIE = 'hub_device'
LOCK = threading.Lock()
TODAY_TIMEOUT = 4.5
SOURCE_WORKERS = ThreadPoolExecutor(max_workers=3, thread_name_prefix='hub-source')


def now():
    return datetime.now().astimezone()


def iso(dt):
    return dt.isoformat(timespec='seconds')


class Store:
    """Small JSON documents written atomically; one lock for all writers."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def read(self, name, default):
        path = self.dir / (name + '.json')
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            return default

    def write(self, name, value):
        path = self.dir / (name + '.json')
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix='.' + name)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(value, handle, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


DEFAULT_SETTINGS = {
    'clock24h': False, 'units': 'F', 'idleMinutes': 3, 'photoSeconds': 30,
    'quietStart': '22:00', 'quietEnd': '06:00', 'returnTodayMinutes': 2,
}

SAMPLE_SHOPPING = [
    ('Avocados', '3', 'Produce'), ('Bananas', '1 bunch', 'Produce'), ('Tomatoes', '4', 'Produce'),
    ('Milk', '1 gal', 'Dairy'), ('Eggs', '12', 'Dairy'), ('Coffee beans', '1 bag', 'Pantry'),
    ('Pasta', '2 boxes', 'Pantry'), ('Paper towels', '6 rolls', 'Household'),
]

QUICK_ADD = ['Bread', 'Yogurt', 'Apples', 'Dish soap']

CALENDARS = [
    {'id': 'family', 'name': 'Family', 'color': 'blue'},
    {'id': 'work', 'name': 'Work', 'color': 'orange'},
    {'id': 'school', 'name': 'School', 'color': 'teal'},
    {'id': 'sports', 'name': 'Sports', 'color': 'purple'},
]


def sample_events(start):
    """Recurring sample week anchored to the current local day."""
    day0 = start.replace(hour=0, minute=0, second=0, microsecond=0)
    plan = [
        (0, 8, 0, 30, 'Team standup', 'work', ''), (0, 12, 0, 60, 'Lunch with Sarah', 'family', ''),
        (0, 16, 30, 60, 'Soccer practice', 'sports', 'Field 2'), (0, 18, 0, 60, 'Dinner at home', 'family', ''),
        (1, 9, 0, 60, 'Dentist', 'family', ''), (1, 9, 30, 60, 'School concert', 'school', 'Auditorium'),
        (1, 14, 0, 45, 'Grocery pickup', 'family', ''), (2, 8, 0, 180, 'Hike with friends', 'family', ''),
        (2, 13, 0, 120, 'Soccer game', 'sports', ''), (3, 10, 0, 60, 'Brunch', 'family', ''),
        (4, 8, 0, 30, 'Team standup', 'work', ''), (5, 15, 30, 60, 'Piano lesson', 'school', ''),
        (6, 19, 0, 90, 'Book club', 'family', ''),
    ]
    events = []
    for offset, h, m, minutes, title, cal, where in plan:
        begin = day0 + timedelta(days=offset, hours=h, minutes=m)
        events.append({'id': f'e{offset}{h:02d}{m:02d}', 'title': title, 'calendar': cal, 'location': where,
                       'start': iso(begin), 'end': iso(begin + timedelta(minutes=minutes)), 'allDay': False})
    for offset, title, cal in ((1, 'No school', 'school'), (2, 'Grandma visiting', 'family')):
        begin = day0 + timedelta(days=offset)
        events.append({'id': f'a{offset}', 'title': title, 'calendar': cal, 'location': '', 'allDay': True,
                       'start': iso(begin), 'end': iso(begin + timedelta(days=1))})
    return events


def sample_weather(at):
    hour = at.replace(minute=0, second=0, microsecond=0)
    temps = [62, 64, 66, 68, 70, 71, 70, 66, 63, 60, 58, 57]
    pops = [0, 0, 5, 10, 20, 30, 45, 60, 55, 40, 20, 10]
    kinds = ['sun'] * 4 + ['cloud'] * 3 + ['rain'] * 3 + ['cloud'] * 2
    hourly = [{'time': iso(hour + timedelta(hours=i)), 'temp': temps[i], 'pop': pops[i], 'kind': kinds[i]}
              for i in range(12)]
    days = [(72, 54, 60, 'rain', 'Rain later'), (68, 52, 20, 'cloud', 'Cloudy'), (65, 50, 70, 'rain', 'Showers'),
            (66, 51, 30, 'cloud', 'Mostly cloudy'), (70, 53, 0, 'sun', 'Sunny'), (71, 55, 5, 'sun', 'Sunny'),
            (69, 54, 15, 'cloud', 'Cloudy')]
    base = at.replace(hour=0, minute=0, second=0, microsecond=0)
    daily = [{'date': iso(base + timedelta(days=i)), 'hi': hi, 'lo': lo, 'pop': pop, 'kind': kind, 'summary': s}
             for i, (hi, lo, pop, kind, s) in enumerate(days)]
    return {
        'source': 'sample', 'location': '[Home location]', 'provider': '[Provider]',
        'observedAt': iso(at - timedelta(minutes=7)), 'forecastAt': iso(at - timedelta(minutes=12)),
        'current': {'temp': 62, 'feelsLike': 60, 'kind': 'sun', 'summary': 'Clear', 'wind': '5 mph',
                    'humidity': 48, 'uv': '2 Low', 'sunrise': '7:18 AM', 'sunset': '6:32 PM'},
        'hourly': hourly, 'daily': daily, 'alerts': [],
    }


SAMPLE_HOME = {
    'contacts': [
        {'id': 'front', 'name': 'Front door', 'open': False},
        {'id': 'back', 'name': 'Back door', 'open': True, 'openMinutes': 12},
        {'id': 'patio', 'name': 'Patio door', 'open': False},
    ],
    'hub': {'name': 'Tapo H100 hub', 'online': True},
    'scenes': [
        {'id': 'good_morning', 'name': 'Good Morning', 'lights': {'living': True, 'kitchen': True, 'bedroom': False, 'twinkly': False}},
        {'id': 'movie_night', 'name': 'Movie Night', 'lights': {'living': True, 'kitchen': False, 'bedroom': False, 'twinkly': True}},
        {'id': 'all_off', 'name': 'All Off', 'lights': {'living': False, 'kitchen': False, 'bedroom': False, 'twinkly': False}},
    ],
    'lights': [
        {'id': 'living', 'name': 'Living room', 'detail': 'Govee · 2 bulbs', 'on': True, 'brightness': 70},
        {'id': 'kitchen', 'name': 'Kitchen', 'detail': 'Govee · 3 bulbs', 'on': True, 'brightness': 100},
        {'id': 'bedroom', 'name': 'Bedroom', 'detail': 'Govee · 1 bulb', 'on': False, 'brightness': 40},
        {'id': 'twinkly', 'name': 'Twinkly lights', 'detail': 'Seasonal', 'on': False, 'brightness': None},
    ],
    'cameras': [
        {'id': 'entry', 'name': 'Entryway · C110'},
        {'id': 'backyard', 'name': 'Backyard · C246D'},
    ],
    'doorbell': {'name': 'Doorbell (D205)', 'verified': False},
}

QUOTES = [
    {'text': 'Well done is better than well said.', 'author': 'Benjamin Franklin', 'source': 'Poor Richard’s Almanack, 1737'},
    {'text': 'The best way out is always through.', 'author': 'Robert Frost', 'source': 'A Servant to Servants, 1914'},
    {'text': 'Hope is the thing with feathers.', 'author': 'Emily Dickinson', 'source': 'Poem 254 (Johnson numbering)'},
    {'text': 'Not all those who wander are lost.', 'author': 'J. R. R. Tolkien', 'source': 'The Fellowship of the Ring, 1954'},
]

PHOTO_TONES = [('#7FA2B3', '#3E5560'), ('#C9B48E', '#6E5536'), ('#9DB58F', '#3F5A37'), ('#B4A3BE', '#5A4366'),
               ('#B9AE9C', '#5C5040'), ('#8FA9BF', '#3A5670'), ('#C4A58C', '#6B4630'), ('#98B3A5', '#3B5C4D')]


def photo_svg(index):
    sky, land = PHOTO_TONES[index % len(PHOTO_TONES)]
    shift = (index * 97) % 400
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 800" preserveAspectRatio="xMidYMid slice">'
            f'<rect width="1280" height="800" fill="{sky}"/>'
            f'<path d="M0 470 L{120 + shift // 3} 250 L{300 + shift // 4} 380 '
            f'L{480 + shift // 5} 150 L{700 + shift // 6} 400 L{900 + shift // 8} 230 '
            f'L1280 430 L1280 800 L0 800Z" fill="{land}" opacity="0.75"/>'
            f'<path d="M0 560 L240 440 L460 530 L700 450 L940 540 L1280 480 L1280 800 L0 800Z" fill="{land}"/>'
            f'<rect y="640" width="1280" height="160" fill="{land}" opacity="0.85"/></svg>')


class Hub:
    def __init__(self, store, integrations=None, photos=None, weather=None, shopping=None):
        self.store = store
        self.integrations = integrations
        self.live_camera = LiveCamera(integrations) if integrations is not None else None
        self.photos = photos
        self.weather_provider = weather
        self.shopping_bridge = shopping
        self.today_jobs = {}
        self.today_lock = threading.Lock()
        if self.store.read('shopping', None) is None:
            created = iso(now())
            self.store.write('shopping', {'items': [
                {'id': uuid.uuid4().hex[:12], 'name': n, 'qty': q, 'category': c, 'done': False, 'created': created}
                for n, q, c in SAMPLE_SHOPPING]})
        self.home = copy.deepcopy(SAMPLE_HOME)

    def settings(self):
        value = dict(DEFAULT_SETTINGS)
        value.update(self.store.read('settings', {}))
        return value

    def shopping(self):
        if self.shopping_bridge is not None:
            return self.shopping_bridge.get()
        return {'source': 'local', 'updatedAt': iso(now()), 'categories': list(CATEGORIES), 'quickAdd': QUICK_ADD,
                **self.store.read('shopping', {'items': []})}

    def mutate_shopping(self, change, request_key=None):
        if self.shopping_bridge is not None:
            return self.shopping_bridge.mutate(change, request_key)
        with LOCK:
            data = self.store.read('shopping', {'items': []})
            change(data['items'])
            self.store.write('shopping', data)
        return self.shopping()

    def calendar(self, start, end):
        if self.integrations is not None:
            return self.integrations.calendar(start, end)
        events = [e for e in sample_events(now())
                  if datetime.fromisoformat(e['end']) > start and datetime.fromisoformat(e['start']) < end]
        return {'source': 'sample', 'updatedAt': iso(now()), 'calendars': CALENDARS, 'events': events}

    def weather(self):
        return self.weather_provider.get() if self.weather_provider is not None else sample_weather(now())

    def today_sources(self, day):
        # Reuse in-flight work so concurrent screen refreshes cannot queue more
        # upstream requests. The whole Today response stays below fetch's timeout.
        key = day.isoformat()
        with self.today_lock:
            for name, load in [('calendar', lambda: self.calendar(day, day + timedelta(days=2))),
                               ('weather', self.weather), ('shopping', self.shopping)]:
                old = self.today_jobs.get(name)
                if old is None or old[1].done():
                    self.today_jobs[name] = (key, SOURCE_WORKERS.submit(load))
            jobs = dict(self.today_jobs)
        wait([job[1] for job in jobs.values()], timeout=TODAY_TIMEOUT)
        values, alerts = {}, []
        for name, (job_key, future) in jobs.items():
            try:
                if not future.done() or job_key != key:
                    raise SourceUnavailable('Refresh pending')
                values[name] = future.result()
            except SourceUnavailable:
                values[name] = (empty_weather('failed') if name == 'weather' else
                                {'source': 'failed', 'items': []} if name == 'shopping' else
                                {'source': 'failed', 'events': [], 'calendars': []})
                alerts.append({'id': name + '-offline', 'severity': 'error',
                               'text': name.title() + ' unavailable', 'view': name,
                               'detail': 'Retry in ' + name.title()})
        return values['calendar'], values['weather'], values['shopping'], alerts

    def status(self):
        t = now()
        sources = [
            {'id': 'calendar', 'name': 'Calendar', 'state': 'sample', 'updatedAt': iso(t)},
            {'id': 'weather', 'name': 'Weather', 'state': 'sample', 'updatedAt': iso(t)},
            {'id': 'photos', 'name': 'Aura photos', 'state': 'sample', 'updatedAt': iso(t)},
            {'id': 'shopping', 'name': 'Shopping', 'state': 'current', 'updatedAt': iso(t)},
            {'id': 'home', 'name': 'Home Assistant', 'state': 'sample', 'updatedAt': iso(t)},
        ]
        if self.integrations is not None:
            for source in sources:
                if source['id'] in ('calendar', 'home'):
                    source.update(self.integrations.health.get(source['id'], {'state': 'failed', 'updatedAt': None}))
        if self.photos is not None and self.photos.enabled:
            next(source for source in sources if source['id'] == 'photos').update(self.photos.status())
        if self.weather_provider is not None:
            next(source for source in sources if source['id'] == 'weather').update(self.weather_provider.health)
        if self.shopping_bridge is not None:
            next(source for source in sources if source['id'] == 'shopping').update(self.shopping_bridge.health)
        return {'sources': sources}

    def home_data(self):
        if self.integrations is not None:
            return self.integrations.home()
        return {'source': 'sample', 'updatedAt': iso(now()), **self.home, 'alerts': self.alerts()}

    def alerts(self):
        if self.integrations is not None:
            return []
        found = []
        for contact in self.home['contacts']:
            if contact['open'] and contact.get('openMinutes', 0) >= 10:
                found.append({'severity': 'warn', 'text': contact['name'] + ' is open',
                              'detail': f"{contact['openMinutes']} min", 'view': 'home'})
        return found

    def home_action(self, body):
        if self.integrations is not None:
            return self.integrations.action(body)
        kind = body.get('kind')
        if kind == 'light':
            light = next((item for item in self.home['lights'] if item['id'] == body.get('id')), None)
            if light is None or type(body.get('on')) is not bool:
                raise ValueError('unknown light')
            light['on'] = body['on']
            return {'result': 'confirmed', 'message': light['name'] + (' on' if light['on'] else ' off')}
        if kind == 'scene':
            scene = next((s for s in self.home['scenes'] if s['id'] == body.get('id')), None)
            if scene is None:
                raise ValueError('unknown scene')
            for light in self.home['lights']:
                light['on'] = scene['lights'][light['id']]
            return {'result': 'confirmed', 'message': scene['name']}
        raise ValueError('unsupported action')


NAME = re.compile(r'^[^\x00-\x1f]{1,60}$')


def clean_item(body):
    if not all(isinstance(body.get(key, ''), str) for key in ('name', 'qty', 'notes')):
        raise ValueError('item fields')
    name = body.get('name', '').strip()
    qty = body.get('qty', '').strip()[:30]
    notes = body.get('notes', '').strip()
    if len(notes) > 120 or any(ord(c) < 32 for c in notes):
        raise ValueError('item notes')
    category = body.get('category') if body.get('category') in CATEGORIES else 'Other'
    if not NAME.fullmatch(name):
        raise ValueError('item name')
    return name, qty, category, notes


def load_token(path):
    """Read the device token, creating a random one (mode 0600) on first use."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_urlsafe(32) + '\n')
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise SystemExit(f'{path}: token must be an owner-only regular file (mode 0600)')
    token = path.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', token):
        raise SystemExit(f'{path}: token must be at least 32 URL-safe characters')
    return token


def make_handler(hub, allowed, token=None):
    class Handler(SimpleHTTPRequestHandler):
        server_version = 'HomeHub/0.1'
        sys_version = ''

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(STATIC), **kwargs)

        def log_message(self, format, *args):
            pass

        def peer_permitted(self):
            peer = ipaddress.ip_address(self.client_address[0])
            return peer.is_loopback or any(peer in net for net in allowed)

        def token_matches(self, value):
            return token is not None and hmac.compare_digest(value.encode(), token.encode())

        def allowed(self):
            peer = ipaddress.ip_address(self.client_address[0])
            if peer.is_loopback:
                return True
            if self.peer_permitted():
                if token is None:
                    return True
                jar = SimpleCookie()
                try:
                    jar.load(self.headers.get('Cookie', ''))
                except CookieError:
                    pass
                if TOKEN_COOKIE in jar and self.token_matches(jar[TOKEN_COOKIE].value):
                    return True
            self.send_error(HTTPStatus.FORBIDDEN)
            return False

        def pair(self, query):
            # The frame opens /pair?token=... on launch; a valid token becomes an
            # HttpOnly cookie, so later requests and the page itself carry no secret.
            try:
                values = parse_qs(query, max_num_fields=2).get('token', [])
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if not self.peer_permitted() or len(values) != 1 or not self.token_matches(values[0]):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            self.send_response(HTTPStatus.FOUND)
            self.send_header('Set-Cookie', f'{TOKEN_COOKIE}={token}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict')
            self.send_header('Location', '/')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store' if self.path.startswith(('/api/', '/pair', '/camera/')) else 'max-age=300')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            super().end_headers()

        def reply(self, value, status=200):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def body(self):
            # A JSON content type forces a CORS preflight, which this server never
            # answers, so other web pages on an allowed machine cannot write here.
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('content type')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('body size')
            try:
                value = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError) as error:
                raise ValueError('invalid JSON') from error
            if not isinstance(value, dict):
                raise ValueError('body shape')
            return value

        def do_HEAD(self):
            if self.allowed():
                super().do_HEAD()

        def do_GET(self):
            path, _, query = self.path.partition('?')
            if path == '/pair':
                return self.pair(query)
            if not self.allowed():
                return
            try:
                params = {k: v[0] for k, v in parse_qs(query, max_num_fields=8).items()}
                if path == '/api/today':
                    t = now()
                    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
                    calendar, weather, shopping, source_alerts = hub.today_sources(day)
                    events = [e for e in calendar['events']
                              if not e['allDay'] and datetime.fromisoformat(e['end']) > t
                              and datetime.fromisoformat(e['start']) < t + timedelta(days=1)][:4]
                    shop = [i for i in shopping['items'] if not i['done']]
                    shop.sort(key=lambda i: i['created'], reverse=True)
                    q = QUOTES[t.toordinal() % len(QUOTES)]
                    self.reply({'source': 'local' if hub.integrations is not None else 'sample',
                                'calendarSource': calendar.get('source'), 'now': iso(t), 'events': events, 'calendars': calendar['calendars'],
                                'shoppingSource': shopping.get('source'), 'shoppingOpen': len(shop), 'shoppingTop': shop[:3], 'quote': q,
                                'weather': weather, 'alerts': hub.alerts() + source_alerts})
                elif path == '/api/calendar':
                    start = datetime.fromisoformat(params['from'])
                    if start.tzinfo is None:
                        start = start.astimezone()
                    days = max(1, min(42, int(params.get('days', '3'))))
                    self.reply(hub.calendar(start, start + timedelta(days=days)))
                elif path == '/api/shopping':
                    self.reply(hub.shopping())
                elif path == '/api/weather':
                    self.reply(hub.weather())
                elif path == '/api/quotes':
                    self.reply({'quotes': QUOTES, 'todayIndex': now().toordinal() % len(QUOTES)})
                elif path == '/api/photos/manifest':
                    if hub.photos is not None and hub.photos.enabled:
                        self.reply(hub.photos.manifest())
                    else:
                        self.reply({'source': 'sample', 'syncedAt': iso(now()), 'collections': ['All', 'Family', 'Trips', 'Seasonal'],
                                    'photos': [{'id': f'p{i:02d}', 'collections': ['All', ['Family', 'Trips', 'Seasonal'][i % 3]]}
                                               for i in range(16)]})
                elif match := re.fullmatch(r'/photos/([a-f0-9]{32})(\.thumb)?', path):
                    if hub.photos is None or not hub.photos.enabled:
                        return self.reply({'error': 'not found'}, 404)
                    try:
                        raw = hub.photos.read(match[1], thumbnail=bool(match[2]))
                    except FileNotFoundError:
                        return self.reply({'error': 'not found'}, 404)
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                elif re.fullmatch(r'/photos/p\d{2}\.svg', path):
                    raw = photo_svg(int(path[9:11])).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/svg+xml')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                elif path == '/api/home':
                    self.reply(hub.home_data())
                elif match := re.fullmatch(r'/camera/live/([a-f0-9]{32})/(.+)', path):
                    if hub.live_camera is None or query:
                        return self.reply({'error': 'not found'}, 404)
                    raw, kind = hub.live_camera.resource(match[1], match[2])
                    self.send_response(200)
                    self.send_header('Content-Type', kind)
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                elif match := re.fullmatch(r'/camera/([a-f0-9]{16})\.jpg', path):
                    if hub.integrations is None:
                        return self.reply({'error': 'not found'}, 404)
                    raw = hub.integrations.camera_image(match[1])
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                elif path == '/api/settings':
                    self.reply(hub.settings())
                elif path == '/api/status':
                    self.reply(hub.status())
                elif path.startswith('/api/'):
                    self.reply({'error': 'not found'}, 404)
                else:
                    super().do_GET()
            except SourceUnavailable as error:
                self.reply({'error': str(error)}, 410 if isinstance(error, CameraInactive) else 503)
            except (KeyError, ValueError):
                self.reply({'error': 'bad request'}, 400)

        def do_POST(self):
            if not self.allowed():
                return
            try:
                body = self.body()
                if self.path == '/api/shopping':
                    name, qty, category, notes = clean_item(body)
                    item = {'id': uuid.uuid4().hex[:12], 'name': name, 'qty': qty, 'category': category,
                            'notes': notes, 'done': False, 'created': iso(now())}
                    result = hub.mutate_shopping(lambda items: items.append(item), body.get('requestKey'))
                    if hub.shopping_bridge is None:
                        result = dict(result, addedId=item['id'])
                    self.reply(result)
                elif self.path == '/api/shopping/clear':
                    self.reply(hub.mutate_shopping(lambda items: items.__setitem__(slice(None), [i for i in items if not i['done']])))
                elif self.path == '/api/camera/live':
                    if hub.live_camera is None:
                        return self.reply({'error': 'Camera not configured'}, 404)
                    self.reply(hub.live_camera.start(body.get('id')))
                elif self.path == '/api/camera/stop':
                    if hub.live_camera is None or not re.fullmatch(r'[a-f0-9]{32}', str(body.get('session', ''))):
                        return self.reply({'error': 'bad request'}, 400)
                    self.reply(hub.live_camera.stop(body['session']))
                elif self.path == '/api/home/action':
                    if hub.integrations is None:
                        time.sleep(0.25)  # sample adapter latency
                    self.reply(hub.home_action(body))
                elif self.path == '/api/settings':
                    current = hub.settings()
                    for key, value in body.items():
                        if key not in DEFAULT_SETTINGS or type(value) is not type(DEFAULT_SETTINGS[key]):
                            raise ValueError('setting type')
                        if key == 'units' and value not in ('F', 'C'):
                            raise ValueError('units')
                        if key in ('quietStart', 'quietEnd') and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
                            raise ValueError('quiet hours')
                        current[key] = value
                    current['idleMinutes'] = max(1, min(30, current['idleMinutes']))
                    current['photoSeconds'] = max(10, min(300, current['photoSeconds']))
                    current['returnTodayMinutes'] = max(1, min(30, current['returnTodayMinutes']))
                    with LOCK:
                        hub.store.write('settings', current)
                    self.reply(current)
                else:
                    self.reply({'error': 'not found'}, 404)
            except SourceUnavailable as error:
                self.reply({'error': str(error)}, 503)
            except (KeyError, ValueError, json.JSONDecodeError):
                self.reply({'error': 'bad request'}, 400)

        def do_PATCH(self):
            if not self.allowed():
                return
            try:
                match = re.fullmatch(r'/api/shopping/([a-f0-9]{12})', self.path)
                if not match:
                    return self.reply({'error': 'not found'}, 404)
                body = self.body()
                def change(items):
                    item = next(i for i in items if i['id'] == match.group(1))
                    if 'done' in body:
                        if type(body['done']) is not bool:
                            raise ValueError('done')
                        item['done'] = body['done']
                self.reply(hub.mutate_shopping(change))
            except (StopIteration, ValueError, json.JSONDecodeError):
                self.reply({'error': 'bad request'}, 400)

        def do_DELETE(self):
            if not self.allowed():
                return
            match = re.fullmatch(r'/api/shopping/([a-f0-9]{12})', self.path)
            if not match:
                return self.reply({'error': 'not found'}, 404)
            try:
                self.body()
                self.reply(hub.mutate_shopping(lambda items: items.__setitem__(
                    slice(None), [i for i in items if i['id'] != match.group(1)])))
            except ValueError:
                self.reply({'error': 'bad request'}, 400)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--allow', action='append', default=[], help='extra client address or CIDR (the frame)')
    parser.add_argument('--token-file', default=str(Path.home() / '.config' / 'home-hub' / 'device-token'),
                        help='device token required from --allow clients (created on first use, mode 0600)')
    parser.add_argument('--no-token', action='store_true', help='allow --allow clients without a token (not recommended)')
    parser.add_argument('--config', help='private JSON configuration outside Git')
    args = parser.parse_args()
    config = private_json(args.config) if args.config else {}
    network = config.get('network', {})
    if args.config:
        args.host = network.get('host', args.host)
        args.allow = network.get('allow', args.allow)
    allowed = [ipaddress.ip_network(a, strict=False) for a in args.allow]
    token = None if args.no_token or not allowed else load_token(args.token_file)
    store, ha = Store(DATA), from_config(config)
    shopping = ShoppingBridge(ha, store, CATEGORIES, QUICK_ADD) if ha is not None and config.get('shopping', {}).get('source') == 'homeassistant' else None
    hub = Hub(store, ha,
              PhotoLibrary(DATA / 'photos', enabled=config.get('photos', {}).get('source') == 'aura'),
              Weather(config.get('weather')) if args.config else None, shopping)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(hub, allowed, token))
    extra = ''.join(', ' + str(address) for address in allowed)
    guard = f'; LAN clients need the token in {args.token_file}' if token else ''
    print(f'Home Hub on http://{args.host}:{server.server_port} (allowed: loopback{extra}{guard})', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
