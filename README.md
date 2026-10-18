# Humblestead Home Hub

A no-build, local kitchen dashboard for a 1280 × 800 landscape photo frame.
The backend uses Python's standard library; the frontend is plain JavaScript.

All eight views and the idle/screensaver/night modes work. Shopping and settings
persist locally. The default demo uses sample calendar/weather/photos/devices;
the deployed integration configuration shows empty calendars/devices until setup.
Live Open-Meteo weather is configured on the deployed frame. The dashboard still
needs the remaining device enrollment and Aura login.

**2026-10-15 deployment update:** the frame now has WebView 106 and the kiosk,
and the dashboard runs as an enabled user service over Wi-Fi with frame-IP and
device-cookie checks. The iCloud/HA adapter is implemented, iCloud is authenticated in HA, and two
family calendars are connected through the dedicated HA credential. See
[`INTEGRATIONS.md`](INTEGRATIONS.md) for setup and verified limitations.

## Run

```sh
python3 server.py
# Open http://127.0.0.1:8099/
```

For disposable data:

```sh
HOME_HUB_DATA=/tmp/home-hub-demo python3 server.py --port 8100
```

The stage scales to fit the browser for desktop testing. Runtime dependencies:
Python 3.13 and a browser with ES2020/fetch/AbortController support (target WebView 106).
There is no npm install, bundler, CDN or font-service request needed to run the hub.
Three local OFL font faces are in `static/fonts/`, with licenses and provenance.

## Implemented interactions

- Persistent sidebar, active-page indication, sync health, and a global alert strip.
- Eight-second API timeout, bounded in-memory last-good cache, labelled stale data,
  source retry and cold-failure states. Sources refresh every minute without
  interrupting focused inputs or open modals.
- Today clock, conditions/rain window, four upcoming events, shopping preview and quote.
- Day/3-day/Week/Month calendar, date picker, filters, overlap lanes, all-day events,
  current-time marker and read-only details. Month cells open a day-detail list rather
  than squeezing tiny buttons into each cell. Short event blocks have a minimum
  56px height and visual overlaps are included in lane assignment.
- Categorized shopping, quantity/notes, quick add, confirmed check state, per-row
  Saving/Retry, collapsed completed items, clear and five-second delete Undo.
- Observed/forecast labels, horizontally scrollable 12-hour forecast and seven days.
- A daily quote appears automatically on Today; there is no separate Quotes page.
- Photo filters, fullscreen viewer and two-layer crossfade slideshow.
- Sample home contacts/scenes/lights, pending doorbell, honest camera placeholders;
  command confirmation and five-second Undo. Stale home controls are disabled.
  Live allowlisted HA cameras show bounded JPEG overview snapshots with thirty-second
  refresh, outage labels and off-state image clearing. The enlarged viewer plays
  private HLS video through HA, with explicit lifecycle cleanup.
- Persisted display/quiet-hour settings, source Retry, diagnostics and a two-finger
  three-second admin hold. Admin currently explains server setup; it does not exit
  Android or expose credentials.
- Idle return to Today, then screensaver/night; tap hint and upward-swipe wake to Today;
  dark-clock night mode with tomorrow's first timed event and alerts.

Inactivity follows the handoff's **sequential** state chain: another tab returns to
Today after `returnTodayMinutes` (default 2), then spends `idleMinutes` (default 3)
on Today before screensaver/night. Starting on Today uses its 3-minute delay directly.
Quiet hours select night mode when idle; physical brightness needs the later kiosk
integration. Wake always restarts the idle timer.

All API text is escaped before rendering, with a second HTML/attribute allowlist.
Only same-origin opaque photo routes and fetched camera blob URLs are allowed as image sources. The browser
never talks directly to Home Assistant, Aura or Google.

## Tests

Backend tests have no extra dependencies, use isolated temporary stores and HTTP
servers, and do not touch `data/`:

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Optional developer-only Chromium UI tests use Playwright. Install the test tools
outside this repo so production remains dependency-free:

```sh
npm install --prefix /tmp/home-hub-browser playwright@1.64.0
/tmp/home-hub-browser/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui.cjs
# Optional sample-only screenshots:
SNAPSHOTS=/tmp/home-hub-screens NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui.cjs
```

The UI test starts its own backend on an ephemeral loopback port with temporary
data. It checks all views, shopping persistence/escaping/retry/Undo, calendar
filters/scroll/detail, cached failures and timeout, photo wake/idle/night, home
confirmation/Undo, settings, admin hold, scaling and absence of external requests.

**Test limitations:** Chromium is a current desktop build with an Android 6 /
Chrome 106 user-agent string, not the actual WebView-106 engine or Android emulator.
Hardware touch, brightness, memory, soak behavior, real data, and the integration
acceptance tests in v1.0 §8.2 are still outstanding. Visual checks are against the
local mock specifications, not automated pixel-diff tests.

## Next work / safety

See [`HANDOFF.md`](HANDOFF.md), [`design/README.md`](design/README.md),
[`design/requirements-v1.1.md`](design/requirements-v1.1.md),
[`FRAME_INSTALL_PLAN.md`](FRAME_INSTALL_PLAN.md), and
[`LESSONS_LEARNED.md`](LESSONS_LEARNED.md).

Read-only USB/ADB diagnosis (serials and network addresses are omitted):

```sh
python3 scripts/diagnose-frame.py
# Reconnect with a proven data cable while watching:
python3 scripts/diagnose-frame.py --watch 60
```

Exit 0 means an authorized ADB target exists, **not** that its identity has been
verified. Exit 2 means access is unresolved; the printed category distinguishes
missing USB enumeration from permissions, authorization, stock USB without ADB,
and FEL. This script never installs or flashes anything.

Before committing, stage the intended files and run
`python3 scripts/check-repo-safety`. The scan refuses runtime/secret-like paths,
symlinks and unknown binaries; only the three hash-verified, licensed font files
are explicitly allowed. It supplements manual review, not a secrecy guarantee.

Enable the versioned commit/push guards after cloning:

```sh
git config core.hooksPath .githooks
python3 scripts/check-repo-safety --all-index --all-history
```

The commit hook checks staged files; the push hook checks the full index and every
reachable historical file version plus commit/tag messages. GitHub CI repeats the
full audit. Hooks can be bypassed, and CI runs after upload, so keep credentials
under `~/.config/home-hub/` and runtime photos/data outside the checkout. Ignore
rules and scanners reduce mistakes; they cannot guarantee detection of every
possible secret. Keep the repository private.

Next setup steps: authenticate the Aura mirror and finish the remaining device enrollment. HA to-do with an offline queue is
still planned. The deployed Shopping list now shares names/checkmarks with HA;
quantity, notes and category remain local. The original local list is retained.

## Frame kiosk (USB)

The frame (PF1007L, April firmware) now has persistent root USB ADB, WebView 106 and
the `kiosk/` app as its Home launcher; see [`FRAME_INSTALL_PLAN.md`](FRAME_INSTALL_PLAN.md)
for what was changed and how to undo each step. To show the dashboard over USB:

```sh
python3 server.py                 # loopback only
scripts/frame-usb-link            # keeps the frame's localhost:8099 mapped to this host
```

Rebuild/redeploy the app with `kiosk/build.sh` and `adb -d install -r kiosk/build/home-hub-kiosk.apk`
(the signing key in `~/.config/home-hub/` must be kept for updates). A three-finger hold
for 2 s opens Android Settings; Settings → Home switches back to AiMOR.

AiMOR and the vendor updater/test packages are disabled on the deployed frame.
Keep those packages disabled and preserve the network restrictions when using Wi-Fi.

Default binding is loopback. LAN deployment with `--allow` is **not authentication**;
keep the frame isolated and the port firewalled, and use a device token if sharing
the network. Do not expose this prototype to the Internet.

## Aura photos

Read-only Aura photo mirroring is implemented. Its separate worker caches resized,
metadata-free JPEGs and thumbnails; Photos and the screensaver use those local
copies. The original Aura frame and cloud library are not changed. To connect:

```sh
scripts/install-aura-runtime  # already installed on this host
scripts/aura-setup            # existing Aura login + source frame selection
```

The helper hides password input, saves only a private session token, performs the
first sync and then enables fifteen-minute refreshes. No personal Aura account is
connected yet. Add iPhone photos with the official Aura app to the selected frame
and the mirror picks them up after sync. [Protocol and operation](docs/aura-protocol.md).

Full backend/image tests: `~/.local/share/home-hub/aura-venv/bin/python -m unittest discover -s tests -v`.
The normal stdlib-only test run skips the five Pillow-dependent test methods when
Pillow is absent; the dedicated-runtime verification now runs 101 tests with no skips.
Photo browser flow: `NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui-aura.cjs`.

Camera browser flow: `NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui-camera.cjs`.

Live video runtime: `scripts/install-stream-runtime` installs one hash-pinned
websocket dependency and a service interpreter drop-in. hls.js is served locally;
ordinary Python runs retain the other dashboard features without that runtime.

Optional Govee cloud bulbs: `python3 scripts/configure-govee` accepts a key at a
hidden local prompt, discovers official cloud light capabilities, and requires
explicit selection of up to four lights. API keys stay in the private secrets
file. This is an independent dashboard connector, not an installed HA custom
integration. Browser QA: `NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui-govee.cjs`.


Hourly photo sampling keeps up to 300 Aura photos plus thumbnails. Old local JPEG
copies are removed after a successful sample replacement. Activate with the
installed hourly Aura timer after owner-local `scripts/aura-setup`.
The tablet also stores the current 300 normalized photos and thumbnails in its
private WebView IndexedDB (256 MB cap). A complete new sample replaces the previous
one atomically; failed downloads keep the previous sample. Photos can reopen from
that stored copy after app reload when the photo server is unreachable. Disabling
the photo source or publishing an empty sample clears the device copy and cancels
older downloads. Clearing kiosk app data also removes device-stored photos. The
server remains the bridge for obtaining new hourly samples; app shell availability
while the whole dashboard server is offline is not guaranteed. See the current
[photo storage policy](docs/aura-protocol.md#current-storage-policy--hourly-random-sample-2026-10-18).

Recipes: open **Recipes → Find on web**, paste a public HTTPS recipe URL, then choose **Focus
mode**. Ingredients and numbered steps can be checked off; larger text and source
sharing are available. **Reader link** opens directly in the clean reader on a
browser already authorized for this private dashboard. Publisher pages must
provide Schema.org Recipe JSON-LD; blocked/login-only pages are not bypassed.
Save imported previews or create recipes by hand in the Recipes catalog. Saved
recipes persist on the server (up to 200) and are never evicted by new imports;
only the five unsaved previews rotate. Existing recent recipes are treated as
saved on migration. Search titles/tags, edit ingredients/steps/notes and delete
recipes with confirmation. Reader links use a stable recipe ID and reopen the
stored text without contacting the publisher. The dashboard server must remain
reachable; this does not provide offline access when the server is unavailable.

Recipe data lives in the private runtime data directory, outside Git. Writes are
atomic; stale edits/deletes receive a conflict instead of overwriting another
window. Corrupt data is preserved and blocks changes rather than resetting the
catalog. New recipes are bounded to 24 KB each; the catalog limit is 20 MB
to accommodate larger recipes retained from the previous reader. Lists send
metadata only; full text is fetched when a recipe opens. No publisher images or
page archives are downloaded.

**Open Recipe Tracker** launches a local copy of the owner's published demo build.
Install it with `python3 scripts/install-recipe-tracker`: three hash-pinned public
assets (about 544 KB total) are verified and stored outside Git. The local route
uses the existing dashboard admission rules and blocks provider/network calls;
no new browser engine or service port is installed. Its browser-local recipe
library is separate from the dashboard's server catalog. **Back to dashboard**
returns to Home Hub. No private project source, credentials or remote database is
bundled in this repository. Browser QA: `node tests/ui-recipes.cjs`.


The sidebar has a separate **Browser** tab with search/address entry and an
**Open browser** button. It uses the existing lightweight single-tab WebView
browser in kiosk v0.5. In
**Recipes → Find on web**, enter search words or a website and choose **Search / Browse**. Open
an actual recipe page, then use the native **Read recipe** button to return to
focus reading automatically. **Dashboard** returns without importing. The browser
has an address bar, Back/Forward and Reload, and uses the existing system WebView
rather than installing a new engine. Search uses DuckDuckGo. On ordinary desktop
browsers, search opens a separate tab; copy its recipe URL and paste it back.
To paste on the tablet, press and hold the recipe-link field and choose Paste.

BrowserActivity is unexported and has no JavaScript/native bridge. Unsupported
schemes, IP-literal/local-name URLs, file/content access, mixed content and popup windows
are blocked; certificate validation retains Android defaults. Browser disk cache
and third-party cookies are disabled. Returning a recipe validates its URL again
and leaves the private dashboard boot/pairing URL unchanged. No extra permission
was added. APKs and signing material remain outside Git publication.

The native browser uses ordinary Android web networking, not the server recipe
fetcher’s DNS pinning. Its website-name checks do not promise DNS-rebinding or
private-DNS isolation. The stricter recipe fetch validation still runs on import.
