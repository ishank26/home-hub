"""Optional pinned local copy of the owner's published Recipe Tracker demo."""
import hashlib
from pathlib import Path

BASE = 'https://ishank26.github.io/recipe_tracker/'
ASSETS = {
    'assets/index-CNf58eVH.js': ('7caf9d4f5042c29fb6529c492a14908066be27e7b078eec277d4e756973c8ae0', 'application/javascript'),
    'assets/index-fEXBKe_W.css': ('d2efc305db5ac0d1ba9e1e2e48edfb2a0ab6dc462048a4a7b68778a979139b57', 'text/css'),
    'assets/recipe-artwork-D3q8DtSU.svg': ('44198758f2c141920cbd1a99ad1813c89815a8f6e7a1306e2f276765a50a7a96', 'image/svg+xml'),
}
PREFIX = '/recipe_tracker/'
DIRECTORY = Path.home() / '.local/share/home-hub/recipe-tracker'
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
INDEX = b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recipe Tracker</title><link rel="stylesheet" href="/recipe_tracker/assets/index-fEXBKe_W.css"><link rel="stylesheet" href="/recipe_tracker/hub.css"><script src="/recipe_tracker/compat.js"></script><script type="module" src="/recipe_tracker/assets/index-CNf58eVH.js"></script></head><body><a class="hub-return" href="/">Back to dashboard</a><div id="root"></div></body></html>'''
COMPAT = b'''// randomUUID is otherwise secure-context-only on the tablet's LAN origin.
if (!crypto.randomUUID) crypto.randomUUID = function () {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return hex.slice(0,8)+'-'+hex.slice(8,12)+'-'+hex.slice(12,16)+'-'+hex.slice(16,20)+'-'+hex.slice(20);
};'''
STYLE = b'.hub-return {position:fixed;right:16px;top:8px;z-index:9999;background:#fff;color:#222;padding:12px 16px;border:1px solid #bbb;border-radius:8px;font:16px sans-serif} #root {padding-top:48px}'


def read_asset(name, directory=DIRECTORY):
    digest, kind = ASSETS[name]
    with (Path(directory) / name).open('rb') as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Recipe Tracker asset verification failed')
    return raw, kind


def response(path, directory=DIRECTORY):
    if not path.startswith(PREFIX):
        raise FileNotFoundError()
    name = path[len(PREFIX):]
    if name == '':
        # No half-installed page is served.
        for asset in ASSETS:
            read_asset(asset, directory)
        return INDEX, 'text/html; charset=utf-8'
    if name == 'compat.js':
        return COMPAT, 'application/javascript'
    if name == 'hub.css':
        return STYLE, 'text/css'
    if name not in ASSETS:
        raise FileNotFoundError()
    return read_asset(name, directory)
