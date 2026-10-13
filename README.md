# Humblestead Home Hub

A no-build, local kitchen dashboard for a 1280 × 800 landscape photo frame.
The backend uses Python's standard library; the frontend is plain JavaScript.

**Prototype status:** all eight views and the idle/screensaver/night modes work
against the provided sample APIs. Shopping and settings persist locally. Calendar,
weather, photos and smart-home devices are **samples**, not connected integrations.
No credentials or frame software have been configured.

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
- Verified quote collection, Next and local favorites (storage denial is handled).
- Photo filters, fullscreen viewer and two-layer crossfade slideshow.
- Sample home contacts/scenes/lights, pending doorbell, honest camera placeholders;
  command confirmation and five-second Undo. Stale home controls are disabled.
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
Only same-origin opaque photo routes are allowed as image sources. The browser
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

Next software phase: server-side adapters with explicit owner choices for calendar,
weather/location and entity allowlists; HA to-do with an offline queue. Shopping
currently uses a local store, not that HA queue. Aura sync is a later separate worker.

ADB is installed, but USB detection and `adb devices -l` currently find no frame.
Use the handoff's USB-A-to-USB-C **data** cable guidance. Do not enable frame Wi-Fi
before outbound TCP 7806 is blocked. No frame writes without owner approval and a
verified backup; stop at the first failed hardware check.

Default binding is loopback. LAN deployment with `--allow` is **not authentication**;
keep the frame isolated and the port firewalled, and use a device token if sharing
the network. Do not expose this prototype to the Internet.
