# Humblestead Home Hub: developer handoff

Updated 2026-10-12. Kitchen wall dashboard for a 10.1-inch Humblestead photo frame
(1280 × 800 landscape, older Android, WebView around 106, roughly 1 GB RAM), used by the
whole family. The frame shows the UI; this home server (`maxcaddy`) runs the backend and
holds every credential.

## Links

| What | Where |
|---|---|
| **Mocks: every screen (in this repo)** | [`design/README.md`](design/README.md) has the tokens and a per-screen layout spec. The source of each mock is in `design/mocks/*.dc.html`: Screensaver, Today, Calendar (3-day), Shopping, Weather, Quotes, Photos, SmartHome, Settings, Night and the shared Sidebar, each 1280 × 800. |
| **Requirements v1.1 (in this repo)** | [`design/requirements-v1.1.md`](design/requirements-v1.1.md) |
| Original interactive canvas (owner only) | https://claude.ai/artifact/6ifw6WadCvNHLEYQ6gHqUj is private and not readable by other agents. The repo copies above are the source of truth. |
| Shareable copy of this handoff | [Home Hub Developer Handoff](https://claude.ai/artifact/RpvZoauK2uqB5K2oqzvd2R) (private until shared) |
| Requirements v1.0 (owner) | `~/Downloads/Humblestead_Home_Hub_Feature_Requirements.docx`. v1.1 on the canvas `Main` board supersedes it where tagged *Changed* or *New*. |
| Original visual concept | First mockup set (8 screens); the audit findings are folded into v1.1. |
| Reference repo | [wesbos/photo-frame-dashboard](https://github.com/wesbos/photo-frame-dashboard), inspected at `9dd323e`. Useful parts: `docs/pf1007l-start-here.md` (frame access tests), `docs/allwinner-a33-pf1007l.md` (WebView 106, kiosk, memory), `docs/aimor-remote-root-shell.md` (**read first**), and `dashboard/` (a Vite UI; not reused, because this project has no build step). |
| Server context | `/home/ishank/work/home-server/MEMORY.md`, `/home/ishank/work/maxcaddy/AGENTS.md`: Home Assistant runs on a private bridge with a loopback UI. Camera, person, audio and location data must never enter the Hermes assistant. |

## Current state (verified 2026-10-12)

| Piece | State |
|---|---|
| `server.py` | **Works.** Standard-library Python 3.13 backend; serves `static/` and the JSON API below. Smoke-tested: all GET endpoints return 200; shopping add/check/clear persists to `data/shopping.json` (atomic writes); non-JSON writes are refused (CSRF guard). Binds `127.0.0.1:8099` by default. **All data except shopping is sample data**, marked `"source": "sample"`. |
| `static/app.css` | **Done**: the full design system and every view's styles, matching the mocks. |
| `static/index.html` | **Done**: page shell (`#rail`, `#main`, `#overlay`) loading `app.css` and `app.js`. |
| `static/app.js` | **Phase 1 prototype implemented.** Eight views, cached/stale APIs, alerts, mutations with confirmed states and Undo, settings, screensaver/night/idle/wake. Desktop Chromium UI suite passes. Actual WebView 106/emulator and frame acceptance remain untested. See `README.md` for tests and limitations. |
| `static/fonts/` | **Self-hosted.** Atkinson Hyperlegible 400/700 and one fixed Fraunces italic 400 face; OFL licenses and verified source/output hashes included. |
| Automated tests | **Pass:** nine isolated backend unittest cases and `tests/ui.cjs` Chromium integration suite (Chrome-106 UA, not the old engine). |
| Adapters (Home Assistant, calendar, weather, Aura) | Not started; sample providers live in `server.py`. |
| Frame | **Not detected** on this laptop: no `1f3a` USB device and `adb devices -l` is empty. ADB 34.0.5 is now installed. Nothing has been written to the frame. |
| Version control | Git initialized; `data/`, `__pycache__/`, bytecode, editor locks and optional test dependencies/artifacts are ignored. No commit made yet. |

Run it:

```sh
cd ~/work/home-hub
python3 server.py                       # http://127.0.0.1:8099
HOME_HUB_DATA=/tmp/hub-test python3 server.py --port 8100   # throwaway data
```

## Architecture

```
Frame (kiosk WebView) ──HTTP, LAN, frame IP allowlisted──► server.py on maxcaddy
                                                         ├─ static UI (no build step)
                                                         ├─ data/ (shopping, settings; 0700)
                                                         └─ adapters (server-side only, read secrets from a 0600 file)
                                                              ├─ Home Assistant REST (dedicated non-admin HA user, entity allowlist)
                                                              ├─ Calendar (Google server-side sync or HA calendar entities: open decision)
                                                              ├─ Weather provider
                                                              └─ Aura sync worker (separate process; images → resized, EXIF-stripped copies)
```

Rules that every change must keep:
- The browser never receives a token, password, cookie for another service, or private filename.
- The frame never talks to Home Assistant, Google or Aura directly.
- Camera snapshots stay in this backend and are never forwarded to Hermes.
- Each source has a current, stale or failed state, and stale data is never shown as live.
- A command is shown as done only after the adapter confirms it; until then the UI says "Sending…".

## API contract (implemented in `server.py`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/today` | `now`, next 4 timed `events`, `calendars`, `shoppingOpen`, `shoppingTop` (3 most recent), `quote` (daily rotation), `weather`, `alerts` |
| GET | `/api/calendar?from=<ISO>&days=1..42` | `calendars` (`id`, `name`, `color`: blue/orange/teal/purple) and `events` (`id`, `title`, `calendar`, `location`, `start`, `end`, `allDay`) |
| GET | `/api/shopping` | `items` (`id`, `name`, `qty`, optional `notes`, `category`, `done`, `created`), `categories`, `quickAdd` |
| POST | `/api/shopping` | `{name, qty?, notes?, category?}`; name is 1–60 characters, notes ≤120; unknown categories become `Other` |
| PATCH | `/api/shopping/<id>` | `{done: bool}` |
| DELETE | `/api/shopping/<id>` | The UI must offer Undo by re-adding the item |
| POST | `/api/shopping/clear` | Removes done items |
| GET | `/api/weather` | `current`, `hourly` (12), `daily` (7), `observedAt`, `forecastAt`, `provider`, `alerts` |
| GET | `/api/quotes` | Curated list with verified attributions, plus `todayIndex` |
| GET | `/api/photos/manifest`, `/photos/pNN.svg` | Sample manifest and SVG placeholders; Phase 3 replaces them with real `/photos/<opaque-id>` JPEGs |
| GET | `/api/home` | `contacts`, `hub`, `scenes`, `lights`, `cameras`, `doorbell` (`verified: false`), `alerts` |
| POST | `/api/home/action` | `{kind: "light", id, on}` or `{kind: "scene", id}`; returns `{result: "confirmed", message}` |
| GET/POST | `/api/settings` | `clock24h`, `units`, `idleMinutes` (1–30), `photoSeconds` (10–300), `quietStart`, `quietEnd`, `returnTodayMinutes` |
| GET | `/api/status` | Per-source `state` and `updatedAt`, for Settings and the sidebar footer |

Writes need `Content-Type: application/json`, a body of at most 16 KB, and come from loopback
or a `--allow` address.

## Implementation plan

### Phase 0: frame access (owner and developer together; **no frame writes without an approved backup**)

See [`FRAME_INSTALL_PLAN.md`](FRAME_INSTALL_PLAN.md) for the current read-only assessment,
identity/backup/approval gates, USB-first dashboard test, deployment and rollback plan.
Current upstream now documents additional April/May firmware variants and a separately
approved temporary-ADB method. The original January build below is the pinned handoff's
reference, not proof of this unit's identity; recheck current guides before each write.

1. On the frame: Settings → About. Record the model and the firmware string.
   PF1007L firmware `…A33…AIMOR.0.20260113` is the tested build; anything else is untested.
2. **Do not put the frame on Wi-Fi** until outbound TCP 7806 is blocked on the router
   (the AiMOR vendor root shell).
3. Connect with a **USB-A to USB-C data cable** in a USB-A port; USB-C to USB-C gives no power or data.
   The owner installs ADB with `sudo apt install adb`. Then check `lsusb | grep -i 1f3a` and `adb devices -l`.
4. Follow the guide's test order: stock ADB over USB, then over the network, then (only if
   both fail) Route U or Route S. Routes U and S write the boot partition: owner approval and a verified
   full backup come first. Stop at the first failed check.
5. Record the actual screen resolution, the WebView version (`chrome://version` or `dumpsys package com.google.android.webview`) and free RAM.

Exit: a reproducible ADB path, a stored backup, and known WebView and RAM figures.

### Phase 1: UI in `static/app.js` (prototype implemented; hardware validation pending)

Plain JavaScript in one file (or a few `<script>` files) with no bundler. ES2020 is fine for
Chrome 106; avoid newer syntax. Build each view from the matching mock board.

1. **Shell:** fit `#stage` (1280 × 800) to the window with `transform: scale()` for desktop
   testing; scale is 1 on the frame. Render the sidebar in this order: Today, Calendar, Shopping,
   Weather, Quotes, Photos, Smart Home, Settings. Mark the active item with `aria-current="page"`. The
   footer shows sync health from `/api/status`.
2. **API helper:** `fetch` with an 8 s timeout. Cache the last good response per endpoint. On
   failure, render from the cache with a stale label; never blank the screen.
3. **Alert strip:** from `/api/today`'s `alerts`, refreshed every 60 s, at the top of `#main` on
   every view. Tapping it opens the alert's `view`.
4. **Views:**
   - **Today**: clock, weather tile, Next up with relative times, shopping preview, quote line. No scroll.
   - **Calendar**:
     - Day, 3 Day (default), Week, Month; Today and previous/next; current-time line;
     - all-day row; legend chips as filters, kept in memory;
     - overlapping events laid out side by side; tap opens a read-only detail modal.
   - **Shopping**:
     - grouped by category; tapping a row toggles `done`, with per-row "Saving…" and then
       "Not saved · Retry" on failure;
     - add field, category select, quick-add chips, "Clear completed";
     - delete with a 5 s Undo.
   - **Weather**: observed and forecast labels, hourly strip with rain %, 7-day cards.
   - **Quotes**: today's quote, Next, Save (favorites in `localStorage`, wrapped in try/catch).
   - **Photos**: collection filter, grid, fullscreen viewer, "Start slideshow" (opens the screensaver).
   - **Smart Home**:
     - contact chips, then scenes, then light tiles, then cameras;
     - commands show "Sending…" and then a toast with the confirmed state and a 5 s Undo;
     - the doorbell shows as "pending verification".
   - **Settings**: source list with Retry, clock and units toggles, idle and photo steppers,
     quiet hours, diagnostics (UA, screen, last error). Admin requires a two-finger hold for 3 s.
5. **State machine:** active → (2 min idle) Today → (`idleMinutes`) screensaver, or night during
   quiet hours.
   - Screensaver: crossfade photos every `photoSeconds` using two `<img>` layers. The clock
     drifts ±8 px each minute. A tap shows "Swipe up to open" for 3 s. A swipe up (dy < −80 px
     within 800 ms) wakes to Today.
   - Night: dark clock, the first event tomorrow, alerts only. A tap wakes to Today.
6. **Performance budget:**
   - one mounted view at a time, with timers cleared on view change;
   - no `backdrop-filter`, crossfades only;
   - under 200 KB of JS;
   - self-host fonts (Atkinson Hyperlegible, Fraunces; both OFL) under `static/fonts/` and
     cut to 3 weights. Until then the CSS falls back to system fonts.

Exit: every v1.0 §8.2 UI test passes in a desktop Chromium (`--user-agent` set to the frame's)
and in an Android 6 / WebView 106 emulator, if available.

### Phase 2: real data adapters (server side)

- Split `server.py` into `server.py` (HTTP), `store.py`, `adapters/` (`calendar.py`, `weather.py`,
  `homeassistant.py`, `shopping.py`) and `samples.py`. Choose the adapter or sample with settings
  in `config.json`.
- Secrets live in `~/.config/home-hub/secrets.json` (mode 0600, outside the repo), loaded at
  startup and never logged or returned.
- Cache each source with a TTL: calendar 5 min, weather 15 min, HA states 15 s. Expose the age in
  `/api/status`.
- **Shopping**: Home Assistant `todo` entity (decision in v1.1), with the local store kept as an
  offline queue.
- **Calendar**: open decision. Either direct Google Calendar sync on the server (richer detail),
  or HA `calendar.*` entities.
- **Weather**: choose the provider and location (open). Show nothing for fields it omits.

Exit: refresh and error states are tested by unplugging each source (v1.0 §6.3 table).

### Phase 3: Aura photo sync (separate worker process)

- The unofficial `zmanowar/auraframes` client is research only. The v1.0 §5.3 review found it logs
  credentials and tokens. Write a minimal read-only client, or harden a pinned fork. Run it as its
  own process with its own data directory.
- Select one existing frame. Poll every 15 min with backoff. Deduplicate by remote asset ID.
- Write resized (1280 × 800 target), EXIF-stripped JPEGs plus a manifest. This needs an image
  library (Pillow), so pin it and hash-check it.
- Serve only through `/photos/<opaque-id>`. Never write to Aura.

Exit: a photo uploaded with the official Aura app appears on the hub after the next sync, and the
real Aura frame is unaffected.

### Phase 4: smart home (Home Assistant)

- Create a dedicated **non-admin** Home Assistant user and a long-lived token for it. HA tokens are
  not scoped, so the backend enforces an entity allowlist from `config.json`. Never hardcode IDs in the UI.
- Discover the real entities first: T110 contacts and H100 hub, Govee H6008, Twinkly, scenes and
  scripts, Tapo C100/C110/C246D cameras, D205 doorbell. Show only what exists.
- Light and scene commands go through `POST /api/services/<domain>/<service>`. Re-read the state and
  report "confirmed" only when it matches.
- Cameras: proxy `/api/camera_proxy/<entity>` snapshots every 30–60 s, at most one live view, and
  never forward them to Hermes. Alerts: contact open longer than [N] min (owner to decide).
- Home Assistant is reachable only from this host (private bridge), so the adapter runs here.

Exit: every shown device returns a confirmed state; unsupported devices are hidden or marked unavailable.

### Phase 5: deployment

- A systemd **user** unit for `server.py` bound to the server's LAN IP with
  `--allow <frame-static-ip>`, plus a firewall rule allowing only the frame to reach port 8099.
- On the frame: kiosk WebView or launcher pointed at `http://<server-lan-ip>:8099/`, boot to
  the dashboard, keep the screen on, and use the brightness schedule. Use the reference repo's
  launcher and kiosk notes.
- Network isolation for the frame (its own VLAN or guest network, AiMOR port blocked).
- A multi-day soak with reboot, idle and wake, and an HA or Internet outage simulation (v1.0 §8.2).

## Known gaps in the current backend

- `tests/test_server.py` now covers endpoints, write validation/persistence, the JSON CSRF guard,
  GET/HEAD/write allowlist policy, settings bounds, confirmed sample commands and timezone-aware
  calendar comparisons. `tests/ui.cjs` uses a temporary `HOME_HUB_DATA` backend for UI checks.
- `/api/home/action` sleeps 250 ms to simulate adapter latency. Remove that with the real adapter.
- Sample light state is held in memory and resets when the server restarts.
- The allowlist is IP-based, which is acceptable on an isolated LAN with a static frame IP. Add a
  per-device token header if the network is shared.
- Calendar sample events repeat relative to "today"; they are not real data.

## Open decisions (owner)

1. Calendar source: direct Google sync, or Home Assistant calendar entities?
2. Door-contact alert threshold, and which doors.
3. Calendar names and colors per family member.
4. Home location, units and quote categories.
5. Weather provider.
6. The exact frame model and firmware (Phase 0).
