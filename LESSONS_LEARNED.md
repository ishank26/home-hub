# Lessons learned and continuation

Recorded 2026-10-12. This is a sanitized engineering record, not a frame deployment
receipt. No private network addresses, device identifiers, credentials or firmware
captures belong here.

## Delivered and verified

- Plain-JavaScript, no-build UI implements all eight views and idle/screensaver/night
  behavior against the provided backend and local design specification.
- Shopping/settings persist locally. Real calendar/weather/Aura/HA adapters remain
  unimplemented; sample badges and confirmed **sample** commands must stay honest.
- Three self-hosted OFL font faces ship with licenses, source hashes and output hashes.
- Nineteen Python tests pass: nine backend HTTP/store/validation tests, six synthetic
  USB/ADB diagnostic tests and four publication-safety tests. The Chromium UI
  integration suite also passes.
- `scripts/diagnose-frame.py` checks Linux USB enumeration and ADB state without
  connecting to a network target or writing to the frame. It omits serials and ADB
  identifiers, and can watch for a physical reconnect.
- `scripts/check-repo-safety` reviews full staged blobs; three licensed OFL font
  binaries are allowed only by their exact documented SHA-256. Runtime/secret paths,
  symlinks and unknown binaries are rejected. Tests cover the font hashes and rejection
  paths. Automated checks supplement, rather than replace, manual review.
- The official GitHub CLI 2.102.0 was staged outside Git in a private user tools
  directory; its release archive SHA-256 was verified against official release metadata.
  No system package or root install was performed.
- GitHub SSH authentication works, but a separate GitHub API/CLI login is required to
  create a repository. Publication must not be described as complete before push and
  remote verification succeed.

## Frontend and backend findings

### 1. Accessible local design files beat private artifact links

The initial canvas link was unreadable outside the owner's session. The owner added
`design/README.md`, `design/requirements-v1.1.md` and source mocks to this checkout.
Those are the implementer's source of truth. The `.dc.html` mocks require their design
runtime; use their inline styles/specification rather than treating them as standalone
web pages. Runtime pages must not copy the mocks' Google Fonts calls.

### 2. A successful response is not automatically a truthful state

GET failures retain last-good data and mark it stale; cold failure shows Retry.
Shopping checkboxes and home tiles retain the last confirmed state while writes are
pending. Failure must never look like success. Sample confirmation is not confirmation
by a real Home Assistant device. IP allowlisting is not authentication on a shared LAN.

### 3. Preserve lifecycle semantics when rewriting code

An AST rewrite of `try/catch` also matched constructs with `finally`; the replacement
omitted the cleanup clause. UI tests caught shopping that saved on the server but never
cleared its busy state or repainted. The shopping/home/settings cleanup clauses were
restored. Lesson: inspect whole matched constructs, preserve `finally` explicitly,
preview structural rewrites, and rerun mutation/failure tests after mechanical changes.
A syntactically valid rewrite and a clean linter are not sufficient evidence.

### 4. Calendar timestamps are instants, not sortable strings

ISO timestamps with different UTC offsets do not compare correctly lexicographically.
Backend calendar-window filtering now parses timestamps before comparison. A regression
fixture crosses a date boundary with `+05:30` versus UTC. More real-adapter timezone/DST
acceptance remains necessary; this fix does not validate real calendar synchronization.

### 5. The 800px budget needs browser checks

The global alert, touch-sized controls and additional metadata can push forecast cards
past the stage even when individual components match mocks. Chromium exposed weather
overflow; metadata moved into the header and spacing was adjusted. Calendar controls
were compacted, short events received 56px tap height with visual overlap lanes, and
month cells open a read-only day list rather than tiny event buttons.

Keep scroll positions across tabs/polls and preserve shopping drafts during saves.
Polls should not destroy a focused input or modal. One complex view is mounted at a time;
entering screensaver unmounts the active view and clears its timers.

### 6. Deterministic UI tests must handle asynchronous DOM replacement

A selector can temporarily disappear while a view loads. Polling assertions need null
checks and should wait for the resulting state rather than immediately reading it.
Resize delivery is asynchronous too. Controlled browser clocks can make CSS animation
screenshots misleading. Test the visible result, not an assumed timing sequence.

### 7. A user-agent string is not an old engine

The suite runs a current Chromium with Android 6 / Chrome 106 UA text. This proves the
functional desktop checks, not actual WebView-106 compatibility, touch performance,
Android brightness, boot behavior, memory or soak stability. Never label those hardware
acceptance tests as passed until they run on the actual frame/emulator.

## USB, ADB and frame safety findings

### 8. Diagnose the layer before applying a fix

On this host ADB is installed and its daemon starts normally. Restarting the daemon
still lists no devices. The owner user is in `plugdev`; attached USB devices have been
authorized and USB2 hubs enumerate. No known Allwinner/Rockchip frame appears in either
`lsusb` or sysfs, and a 30-second USB monitor saw no connection event.

The observed state is **missing USB enumeration**, not proven bad ADB permissions.
Likely possibilities include cable, port, power, connection to another host, or a
board-specific data path; the exact physical cause is **not yet proven**. A missing
udev-rules package cannot by itself explain a frame absent from `lsusb`. Do not claim
that changing permissions, reinstalling ADB, or enabling debugging repaired it.

ADB states need separate treatment:

| Evidence | Meaning / next step |
|---|---|
| No USB candidate and no ADB | Confirm power, proven A-to-C data cable, direct USB-A port and physical reconnect |
| USB `1f3a:1000`, no ADB interface | Data path exists; some stock AiMOR units expose mass storage but not ADB |
| ADB `no permissions` | Now investigate host udev rules/device-node access |
| ADB `unauthorized` | Owner debugging approval, not a cable or driver workaround |
| ADB `offline` | Data/power/daemon communication issue; investigate without flashing |
| USB `1f3a:efe8` | FEL/recovery, not Android ADB or a backup |
| ADB `device` | Access works, but verify that the target is actually this frame before commands |

### 9. Device discovery names are not identity

A network advertisement named `Android.local` was found, but its service advertised a
TV/AirPlay endpoint. It was not treated as the frame and no ADB connection was attempted.
Do not guess a frame IP from a generic hostname, ARP entry, brand or MAC vendor. Use the
owner's About/Status screen or router entry and verify identity before access.

### 10. Prefer a stable, known data/power path

Upstream PF1007L reports recommend USB-A-to-USB-C **data** cables and a direct USB-A
port or powered USB2 hub. Charge-only cables can power the frame without enumeration.
Some C-to-C combinations fail; newer reports show exceptions, so do not turn the
recommendation into an absolute hardware claim. Several deep hub chains are present
on this host; their existence does not prove the frame is attached through them.

Do not reset the frame, short pins, flash boot, or write an SD card to diagnose an
unconfirmed physical cable issue. Those require their own review and owner approval.

### 11. Firmware research must be refreshed before writes

The handoff pinned January `20260113`; current upstream also documents April/May
variants, storage-size differences and a separately approved temporary-ADB procedure
for one April firmware. Some units ship with ADB enabled, others with the same firmware
do not. Always read About and current upstream reports before choosing a route.

Route S on main retains a January-only write guard. Unmerged April reports are not
approved inputs, and editing a hash guard is not a compatibility test. Route U's
structural checks also do not prove an unknown image safe. Stop at mismatches.

### 12. Network and backup gates are not optional

The AiMOR root-command connection on outbound TCP 7806 is a documented hazard. Do not
put the stock frame on Wi-Fi before isolation/blocking is verified. The temporary
vendor-command ADB route is a runtime change exposing root, not read-only discovery.

A boot dump or first-2-GiB SD dump is not a full-device backup. Verify sizes, independent
rereads, hashes, filler checks and compression readback; establish a usable rollback.
Never publish dumps, package-state XML, account databases, Wi-Fi information, signing
keys or full-device hashes. Do not use the protected Crucial X6 for this project.

### 13. First display test should be USB-only and reversible

After identity/access/backup/approval, prefer loopback Python hosting plus ADB reverse
forwarding to frame localhost. This tests rendering without a LAN listener or Wi-Fi
exposure. A WebView upgrade may be needed on a stock WebView-44 unit, but must be a
separate approved system change with the original APK/odex tree preserved. Version
metadata alone does not prove native libraries load or the kiosk renders.

Keep a working Home/launcher recovery path, coordinate native versus web admin gestures,
and test persisted package changes and cold boot before describing a kiosk as deployed.
No launcher, kiosk, WebView, firmware or frame network setting was changed this session.

## Exact continuation

```sh
# Read-only detection; reconnect the frame while this watches:
python3 scripts/diagnose-frame.py --watch 60

# Software checks:
python3 -m unittest discover -s tests -v
node --check static/app.js
NODE_PATH=/tmp/home-hub-browser/node_modules node tests/ui.cjs
```

Next owner inputs: About model/full firmware, ports/power and a proven direct data-cable
connection. If network fallback is needed, verified TCP-7806 isolation plus a positively
identified IP. Then follow `FRAME_INSTALL_PLAN.md` one gated phase at a time.
