"""Small structured recipe reader. Never embeds or executes publisher HTML."""
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin

from integrations import SourceUnavailable

MAX_HTML = 2_000_000
_FETCHES = threading.BoundedSemaphore(2)
_DNS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='recipe-dns')
_DNS_SLOTS = threading.BoundedSemaphore(2)


def safe_url(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r'[\x00-\x20\x7f\\]', url):
        raise ValueError('Enter a public HTTPS recipe link')
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or not p.hostname or p.username is not None or p.password is not None
                or p.port not in (None, 443) or '%' in p.hostname):
            raise ValueError
        host = p.hostname.encode('idna').decode('ascii').lower()
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host):
                raise ValueError
        else:
            if not addr.is_global or getattr(addr, 'ipv4_mapped', None):
                raise ValueError
        netloc = '[' + host + ']' if ':' in host else host
        return urlunsplit(('https', netloc, p.path or '/', p.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('Enter a public HTTPS recipe link') from None


def public_addresses(host, timeout=2):
    if not _DNS_SLOTS.acquire(blocking=False):
        raise SourceUnavailable('Recipe lookup is busy; retry shortly')
    try:
        job = _DNS.submit(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except Exception:
        _DNS_SLOTS.release()
        raise
    job.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        records = job.result(timeout=timeout)
    except (TimeoutError, OSError):
        raise SourceUnavailable('Recipe address could not be resolved') from None
    if not records or len(records) > 64:
        raise ValueError('Unsupported recipe address')
    for _, _, _, _, address in records:
        ip = ipaddress.ip_address(address[0])
        if not ip.is_global or getattr(ip, 'ipv4_mapped', None):
            raise ValueError('Recipe links must resolve only to public addresses')
    return records


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, record, timeout, expired=None):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.record = record
        self.expired = expired or threading.Event()
        self.deadline_socket = None

    def connect(self):
        family, socktype, protocol, _, address = self.record
        raw = socket.socket(family, socktype, protocol)
        self.deadline_socket = raw
        try:
            raw.settimeout(self.timeout)
            if self.expired.is_set():
                raise TimeoutError
            raw.connect(address)  # exact validated address; no second DNS lookup
            if self.expired.is_set():
                raise TimeoutError
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            self.deadline_socket = self.sock
            if self.expired.is_set():
                raise TimeoutError
            self.sock.do_handshake()
        except Exception:
            raw.close()
            raise

    def abort(self):
        sock = self.deadline_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


FETCH_SECONDS = 7


def fetch_html(url):
    if not _FETCHES.acquire(blocking=False):
        raise SourceUnavailable('Recipe reader is busy; retry shortly')
    expired, active = threading.Event(), []
    def interrupt():
        expired.set()
        if active:
            active[0].abort()
    timer = threading.Timer(FETCH_SECONDS, interrupt)
    timer.daemon = True
    timer.start()
    try:
        deadline = time.monotonic() + FETCH_SECONDS
        for _ in range(4):
            url = safe_url(url)
            p = urlsplit(url)
            left = deadline - time.monotonic()
            if left <= 0 or expired.is_set():
                raise SourceUnavailable('Recipe request timed out')
            addresses = public_addresses(p.hostname, timeout=min(2, left))
            left = deadline - time.monotonic()
            if left <= 0:
                raise SourceUnavailable('Recipe request timed out')
            conn = PinnedHTTPS(p.hostname, addresses[0], min(2, left), expired)
            active[:] = [conn]
            if expired.is_set():
                raise SourceUnavailable('Recipe request timed out')
            try:
                conn.request('GET', urlunsplit(('', '', p.path, p.query, '')),
                             headers={'User-Agent': 'HomeHub-RecipeReader/1.0', 'Accept': 'text/html',
                                      'Accept-Encoding': 'identity'})
                response = conn.getresponse()
                if expired.is_set():
                    raise SourceUnavailable('Recipe request timed out')
                if response.status in (301, 302, 303, 307, 308):
                    target = response.getheader('Location')
                    if not target:
                        raise ValueError('Missing recipe redirect')
                    url = safe_url(urljoin(url, target))
                    continue
                if response.status != 200:
                    raise SourceUnavailable('Publisher did not allow recipe reading; try another link')
                if (response.getheader('Content-Type', '').split(';')[0].lower() not in ('text/html', 'application/xhtml+xml')
                        or response.getheader('Content-Encoding', 'identity').lower() != 'identity'):
                    raise ValueError('Unsupported recipe page format')
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise SourceUnavailable('Recipe request timed out')
                    part = response.read1(min(65536, MAX_HTML + 1 - size))
                    if not part:
                        break
                    size += len(part)
                    if size > MAX_HTML:
                        raise ValueError('Recipe page is too large')
                    chunks.append(part)
                charset = response.headers.get_content_charset() or 'utf-8'
                try:
                    source = b''.join(chunks).decode(charset, errors='replace')
                except LookupError:
                    source = b''.join(chunks).decode('utf-8', errors='replace')
                return url, source
            finally:
                conn.close()
        raise ValueError('Too many recipe redirects')
    except (OSError, http.client.HTTPException):
        raise SourceUnavailable('Could not read this recipe securely; try another link') from None
    finally:
        timer.cancel()
        _FETCHES.release()


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)


def plain(value, limit=2000):
    if not isinstance(value, str):
        return ''
    parser = PlainText()
    parser.feed(value[:limit * 4])
    return re.sub(r'\s+', ' ', html.unescape(' '.join(parser.parts))).strip()[:limit]


class RecipeScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active, self.parts, self.scripts = False, [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = dict(attrs).get('type', '').split(';')[0].lower() == 'application/ld+json'
            self.parts = []

    def handle_data(self, text):
        if self.active:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.scripts.append(''.join(self.parts))
            self.active = False


def parse_recipe(source, url):
    parser = RecipeScripts()
    parser.feed(source)
    candidates, remaining = [], 10000
    for script in parser.scripts[:100]:
        try:
            node = json.loads(script)
        except (ValueError, RecursionError):
            continue
        queue = [node]
        while queue:
            remaining -= 1
            if remaining < 0:
                raise ValueError('Recipe metadata is too complex')
            value = queue.pop()
            if isinstance(value, list):
                queue.extend(value)
            elif isinstance(value, dict):
                types = value.get('@type', [])
                if isinstance(types, str):
                    types = [types]
                if isinstance(types, list) and any(t in ('Recipe', 'https://schema.org/Recipe', 'http://schema.org/Recipe') for t in types):
                    candidates.append(value)
                # JSON-LD graph is allowed; arbitrary nested objects are bounded.
                queue.extend(v for v in value.values() if isinstance(v, (dict, list)))
    for recipe in candidates:
        title = plain(recipe.get('name'), 200)
        ingredients = recipe.get('recipeIngredient', [])
        if not isinstance(ingredients, list):
            continue
        ingredients = [plain(x, 500) for x in ingredients[:100] if isinstance(x, str)]
        steps, queue, visited = [], [(recipe.get('recipeInstructions'), 0)], 0
        while queue:
            value, depth = queue.pop(0)
            visited += 1
            if visited > 1000 or depth > 12:
                raise ValueError('Recipe instructions are too complex')
            if isinstance(value, str):
                steps.extend(plain(x) for x in re.split(r'[\r\n]+', value) if plain(x))
            elif isinstance(value, list):
                queue[0:0] = [(x, depth + 1) for x in value[:100]]
            elif isinstance(value, dict):
                if value.get('itemListElement') is not None:
                    queue.insert(0, (value['itemListElement'], depth + 1))
                elif isinstance(value.get('text'), str):
                    steps.append(plain(value['text']))
        ingredients = [x for x in ingredients if x]
        steps = [x for x in steps if x][:100]
        if title and ingredients and steps:
            servings = recipe.get('recipeYield', '')
            if isinstance(servings, list):
                servings = ' / '.join(str(v) for v in servings[:4] if type(v) in (str, int, float))
            elif type(servings) not in (str, int, float):
                servings = ''
            return {'title': title, 'description': plain(recipe.get('description'), 1000),
                    'ingredients': ingredients, 'steps': steps, 'url': safe_url(url),
                    'yield': plain(str(servings), 100),
                    'totalTime': plain(recipe.get('totalTime'), 80)}
    raise ValueError('No structured recipe found. Try the recipe’s own page rather than a search or social link.')


def read_recipe(url):
    url, source = fetch_html(url)
    return parse_recipe(source, url)
