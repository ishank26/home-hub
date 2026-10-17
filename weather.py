"""Bounded server-side Open-Meteo forecast adapter; no account or browser calls."""
import json
import math
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

from integrations import NoRedirect, SourceUnavailable


def condition(code):
    if code == 0:
        return 'sun', 'Clear'
    if code in (1, 2, 3):
        return 'cloud', 'Partly cloudy' if code != 3 else 'Overcast'
    if code in (45, 48):
        return 'cloud', 'Fog'
    if code in (71, 73, 75, 77, 85, 86):
        return 'snow', 'Snow'
    if code in (95, 96, 99):
        return 'rain', 'Thunderstorms'
    return 'rain', 'Rain' if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82) else 'Unknown conditions'


def empty_weather(state='unconfigured'):
    return {'source': state, 'location': '', 'provider': '', 'observedAt': None, 'forecastAt': None,
            'current': {'temp': None, 'kind': 'cloud', 'summary': 'Weather needs setup' if state == 'unconfigured' else 'Weather unavailable'},
            'hourly': [], 'daily': [], 'alerts': []}


class Weather:
    def __init__(self, config):
        self.config = config or {}
        self.enabled = bool(self.config)
        self.zone = ZoneInfo(self.config.get('timezone', 'America/New_York'))
        if self.enabled:
            for key, limit in [('latitude', 90), ('longitude', 180)]:
                v = self.config.get(key)
                if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > limit:
                    raise ValueError('Invalid weather location')
        self.transport = build_opener(ProxyHandler({}), NoRedirect())
        self.lock = threading.Lock()
        self.value = None
        self.loaded = 0
        self.retry_at = 0
        self.health = {'state': 'failed', 'updatedAt': None}

    def request(self):
        params = {k: self.config[k] for k in ('latitude', 'longitude')}
        params.update(timezone=str(self.zone), timeformat='unixtime', temperature_unit='fahrenheit',
                      wind_speed_unit='mph', forecast_days=7,
                      current='temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
                      hourly='temperature_2m,precipitation_probability,weather_code',
                      daily='weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,uv_index_max')
        req = Request('https://api.open-meteo.com/v1/forecast?' + urlencode(params),
                      headers={'User-Agent': 'HomeHub/1.0', 'Accept': 'application/json'})
        with self.transport.open(req, timeout=4) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('Oversized weather response')
            return json.loads(raw)

    def parse(self, data):
        def number(v):
            if type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError('Missing weather value')
            return v

        def stamp(v):
            return datetime.fromtimestamp(number(v), self.zone).isoformat()

        c, h, d = data['current'], data['hourly'], data['daily']
        kind, summary = condition(number(c['weather_code']))
        current = {'temp': number(c['temperature_2m']), 'kind': kind, 'summary': summary}
        for remote, local in [('apparent_temperature', 'feelsLike'), ('relative_humidity_2m', 'humidity')]:
            if c.get(remote) is not None:
                current[local] = number(c[remote])
        if c.get('wind_speed_10m') is not None:
            current['wind'] = str(round(number(c['wind_speed_10m']))) + ' mph'
        hourly, daily = [], []
        now = time.time()
        for i, ts in enumerate(h['time'][:192]):
            if number(ts) < now - 3600 or len(hourly) >= 12:
                continue
            hk, _ = condition(number(h['weather_code'][i]))
            hourly.append({'time': stamp(ts), 'temp': number(h['temperature_2m'][i]),
                           'pop': number(h['precipitation_probability'][i]), 'kind': hk})
        for i, ts in enumerate(d['time'][:7]):
            dk, ds = condition(number(d['weather_code'][i]))
            daily.append({'date': stamp(ts), 'hi': number(d['temperature_2m_max'][i]),
                          'lo': number(d['temperature_2m_min'][i]), 'pop': number(d['precipitation_probability_max'][i]),
                          'kind': dk, 'summary': ds})
        if len(daily) != 7 or len(hourly) != 12:
            raise ValueError('Incomplete forecast')
        for key in ('sunrise', 'sunset'):
            if d.get(key) and d[key][0] is not None:
                current[key] = datetime.fromtimestamp(number(d[key][0]), self.zone).strftime('%I:%M %p').lstrip('0')
        if d.get('uv_index_max') and d['uv_index_max'][0] is not None:
            current['uv'] = number(d['uv_index_max'][0])
        return {'source': 'open-meteo', 'location': str(self.config.get('name', 'Local weather'))[:100],
                'provider': 'Open-Meteo · CC BY 4.0', 'currentLabel': 'Now · model estimate',
                'currentAt': stamp(c['time']), 'observedAt': None,
                'forecastAt': datetime.now(self.zone).isoformat(), 'current': current,
                'hourly': hourly, 'daily': daily, 'alerts': []}

    def get(self):
        if not self.enabled:
            return empty_weather()
        with self.lock:
            now = time.monotonic()
            if self.value and now - self.loaded < 900:
                return self.value
            if now < self.retry_at:
                raise SourceUnavailable('Weather unavailable; retry shortly')
            try:
                value = self.parse(self.request())
            except Exception:
                self.health = {'state': 'stale' if self.value else 'failed',
                               'updatedAt': self.value['forecastAt'] if self.value else None}
                self.retry_at = now + 60
                raise SourceUnavailable('Weather unavailable; retry shortly') from None
            self.value, self.loaded = value, now
            self.health = {'state': 'current', 'updatedAt': value['forecastAt']}
            return value
