# Frame assessment and installation plan

Initial assessment: 2026-10-12. Installation and Wi-Fi updates below supersede
the historical assessment table and original planning gates.

## Observed versus unknown

| Item | Evidence / state |
|---|---|
| Host | Debian/Linux, existing dashboard checkout available |
| ADB | Installed, version 34.0.5; `adb devices -l` lists no devices |
| USB | 2026-10-14: `1f3a:1000` "Android", Mass Storage interface only, no ADB (`diagnose-frame.py`: `usb-without-adb`). Connected through a USB 2.0 hub |
| Recent USB kernel events | No relevant events visible in the accessible last-20-minute journal; an additional 30-second udev USB monitor saw no connection events. Limited journal visibility is not proof of absence |
| Network identity | No positively identified frame IP; mDNS candidate `Android.local` advertises a TV/AirPlay service, not a verified frame. No ADB connection attempted to it. Neighbor-cache entries alone do not identify the frame |
| Model / firmware | 2026-10-14, owner About screen: PF1007L, `…A33-1001-D1024-PF1007L-321-OS-AIMOR.0.20260410`, AiMOR 6.0.78. Exactly matches upstream's tested April units (T3c, one-sector edit, Route U) |
| Ports / cable / power | Unknown; owner physical check needed |
| Android / ABI / WebView / RAM | 2026-10-14, via temporary root network ADB (upstream T3c on an isolated laptop-hosted Wi-Fi; web-only egress, vendor 7806 redirected to the laptop): `sun8i`, Android 6.0.1 / API 23, `armeabi-v7a`, build `…MOB30R 20260410`, 1280×800 @ 160 dpi, stock WebView **44.0.2403.119** (no Google WebView), ~1 GB RAM + 256 MiB zRAM swap, eMMC 30,777,344 sectors, `/system` 1008 MB (396 MB free), `ro.adb.secure=0`, `persist.sys.usb.config=mass_storage` with no `/data/property` override |
| Backup | 2026-10-14: **partial** capture only, from stock recovery's root-ADB window during an owner-approved AiMOR factory reset (user data wiped). Pulled boot, env, misc, recovery (private 0700 directory outside Git; bootloader missed when the window closed). Boot image SHA-256 over 31,028 sectors = `8ffc2a7d…`, matching upstream's tested April units. Not a full-device backup |
| Router protection | Outbound TCP 7806 block not verified; no Wi-Fi enrollment or network ADB attempted |
| Dashboard | Sample-data prototype passes backend and desktop Chromium tests; actual frame engine untested |
| Host dashboard listener | Nothing listening on 8099 at this assessment |
| APK build tools | No Java/Javac, Android platform/build-tools, aapt, zipalign or apksigner found through the inspected PATH/directories; platform-tools available |
| Host backup space | More than 700 GiB available on the internal home filesystem at assessment; no external backup disk used |

**Current state (2026-10-14):** persistent **root USB ADB** works (`1f3a:1001`, `adb -d`). Done by one owner-approved write over temporary T3c network ADB: `persist.sys.usb.config=adb` in `/data/property` (undo: set it back to `mass_storage`, or an AiMOR factory reset clears it). Verified across a reboot; network ADB 5555 closed after reboot. The owner **declined a full backup**; only the partial recovery-window capture exists.

**WebView (2026-10-14, owner-approved, no full backup):** replaced stock 44.0.2403.119 with **106.0.5249.126** (LineageOS `android_external_chromium-webview_prebuilt_arm@4b0ae494a7dd`, APK SHA-256 `e2edc1f8…0980580`), with `lib/arm/*.so` extracted per upstream §6; every staged and live file verified by readback. Original tree (APK + odex) preserved at `/system/homehq-stock-webview`. After reboot Package Manager reports 106 from `/system/app/webview`, no `dlopen` errors, and HTMLViewer renders HTML (its JavaScript is disabled, so JS/ES2020 is unverified until the kiosk). `/system` remounted read-only; 288 MB free.

Undo: remount `/system` rw, `mv /system/app/webview /system/homehq-new-webview`, `mv /system/homehq-stock-webview /system/app/webview`, sync, remount ro, reboot.

**Kiosk (2026-10-14):** `kiosk/` builds a 12.6 KB fullscreen WebView app (`com.homehub.kiosk`, INTERNET permission only) with Debian `openjdk-21-jdk-headless`, `aapt`, `zipalign`, `apksigner`, `android-framework-res` and pinned d8 8.5.35; signing key in `~/.config/home-hub/` (outside Git). Installed as a normal app (`adb -d uninstall com.homehub.kiosk` removes it). With `server.py` on loopback and `adb -d reverse tcp:8099 tcp:8099`, the Today view renders fullscreen at 1280×800 on the frame; no JavaScript errors in logcat (only benign `eglChooseConfig` probe messages); ~63 MB PSS. Exit: three-finger hold for 2 s. **Home launcher (2026-10-14, kiosk v0.2):** the kiosk also declares HOME and was chosen as the preferred Home app ("Always" in the system chooser); AiMOR stays installed. Verified: after reboot the kiosk starts by itself. A three-finger hold opens Android Settings (Settings → Home switches back to AiMOR). `scripts/frame-usb-link` re-creates the `adb reverse` mapping after reboots/replugs (verified). All eight tabs render on the device. Dashboard fix: after a cold start without the server it now retries every 10 s and reloads settings (was: 60 s, and settings stayed at defaults); verified on the frame (recovered 11 s after the link returned).

**2026-10-15 Wi-Fi update:** owner selected Wi-Fi. Verified frame Wi-Fi address,
saved kiosk LAN URL and already-disabled AiMOR/updater/test packages; no package
changes this session. Installed/enabled `home-hub.service` with LAN-interface
binding, exact frame-IP allowlist and existing device cookie. Authenticated frame
Wi-Fi API status succeeds; unpaired request is 403. USB forwarding removed. User
linger is enabled. Service restart passes; host/frame reboot, DHCP reservations,
encrypted or isolated transport for personal data and multi-day soak remain.
See [`INTEGRATIONS.md`](INTEGRATIONS.md). No new firmware writes were performed.
Brand/listing is not proof of the board or firmware.

## 1. Owner physical checks, then read-only discovery

1. On the frame, open Settings → About. Record only the model and full firmware
   string, plus AiMOR version if shown. Avoid sharing serials, QR codes or account details.
2. Describe the ports: USB-C only, or DC power plus a separate USB data/OTG port.
3. Connect with a known **USB-A-to-USB-C data cable** to a direct USB-A computer port.
   For DC-powered units, keep the correct normal power supply connected.
   A charge-only cable and an underpowered hub can hide the device.
4. Let it boot, accept an existing USB-debugging prompt if one appears, and repeat:

   ```sh
   lsusb
   adb devices -l
   ```

5. If still absent, try another proven data cable, direct port/powered USB2 hub,
   and another computer. Do not hold reset, prepare an SD card, factory-reset or
   disassemble the frame just to make this check pass.

Branch on evidence:

- ADB `device`: select that exact target and run the read-only inventory below.
- ADB `unauthorized`: owner handles the on-frame prompt; do not bypass authentication.
- `1f3a:1000`, no ADB: stock USB data works, but ADB is not exposed.
- `1f3a:efe8`: FEL/recovery identity, **not** a working Android shell or backup.
- `2207` or another board: stop the Allwinner procedure and research that board.
- No device: USB diagnosis remains open; a boot patch is not justified yet.

Once a single positively identified ADB target exists, select it explicitly:

```sh
adb -s <confirmed-target> shell id
adb -s <confirmed-target> shell getprop ro.product.model
adb -s <confirmed-target> shell getprop ro.product.cpu.abi
adb -s <confirmed-target> shell getprop ro.build.version.sdk
adb -s <confirmed-target> shell getprop ro.build.fingerprint
adb -s <confirmed-target> shell getprop sys.boot_completed
adb -s <confirmed-target> shell wm size
adb -s <confirmed-target> shell wm density
adb -s <confirmed-target> shell dumpsys package com.android.webview
adb -s <confirmed-target> shell dumpsys package com.google.android.webview
adb -s <confirmed-target> shell 'cat /proc/meminfo; cat /proc/swaps'
```

These are examples for the future confirmed device, not commands executed here.
Keep inventory output private outside Git. Do not blindly dump all properties,
application databases or logs, which may contain credentials and identifiers.

## 2. Network fallback only after the safety gate

Prefer USB. If stock USB ADB is unavailable:

1. Verify a router/VLAN policy blocking the frame's outbound TCP 7806 **before**
   putting it on Wi-Fi. Prefer no Internet access and isolation from other LAN clients.
   A temporary app-level pause may not survive this frame's changing Wi-Fi MAC.
2. Get the IP from the frame Status page or the owner's router client list.
   Do not infer it from a MAC vendor or connect to an unrelated device.
3. Test only that confirmed IP on 5555, then `adb connect` if appropriate.
4. If closed/unauthorized, stop and choose the next route deliberately. No broad
   port scanning, DNS redirection or vendor root-shell commands have been authorized.

Current upstream documents a temporary runtime root-ADB method for April
`20260410` firmware. It is **not read-only**, opens unauthenticated root ADB, and
needs exact model/firmware verification, an isolated controlled network, independent
review, specific owner approval and cleanup. It is a possible separately reviewed
alternative, not an action in this plan.

## 3. Recovery and backup gate

Before any APK install, default-launcher change, package disable, WebView replacement
or flash write:

- Establish a backup/recovery method for the **actual** board and storage layout.
- Store captures in a private mode-0700 directory outside Git, on the internal disk.
  Do not use the protected Crucial X6.
- Verify expected byte counts against live partition/storage sizes, SHA-256,
  independent rereads, and compression/decompression readback. Check for bogus
  `0xCC` filler. Preserve an exact original WebView tree if it may be replaced.
- Document scope: a boot image or the first 2 GiB is **not a full-device backup**.
  If a full backup is impossible, stop and obtain explicit approval for a clearly
  described narrower recovery scope; never silently substitute it.
- Record the exact rollback route. Having an image without a usable restore path
  is not enough to justify flashing.
- Get owner approval for each installation/system/flash phase and review exposure
  and failure paths before execution. Recheck current upstream before each write.

If stock access does not provide sufficient reads, investigate a read-only FEL/
U-Boot full-eMMC backup route after the earlier access tests are resolved. Preparing
or booting a spare recovery SD card needs specific approval; selecting its disk must
be positively verified. Do not modify image-hash, disk-name or size guards.

Route U and Route S are not universal. Current Route S on upstream main retains a
January-only write guard; April alternatives in unmerged PRs are less reviewed.
Do not run Rockchip tools or partition offsets on an A33.

## 4. Least-invasive first rendering test

After access, backup and approval:

1. Use the current browser if compatible. Do not replace WebView unnecessarily.
   The prototype needs an ES2020-capable engine; the documented stock WebView 44
   cannot be assumed sufficient.
2. If needed, build a minimal, locally reviewed WebView kiosk for the verified SDK/ABI.
   Pin downloaded SDK/APK inputs, verify hashes and signatures, and keep the signing
   key outside Git. No unknown APK from a mirror.
3. Keep a working fallback launcher before changing Home defaults or disabling
   vendor apps. Install one component at a time, read back its version/state, and
   verify the actual display before proceeding.
4. Start the existing Python server on **loopback**, with temporary sample data.
5. Add an approved ADB reverse mapping from frame localhost:8099 to host
   localhost:8099; open `http://127.0.0.1:8099/` on the frame.
   This is a USB test, not LAN deployment; the mapping must be recreated after
   ADB/device restart. No host firewall or HA exposure changes are needed.
6. Test every tab, shopping save/reload, modal input, photo crossfades, idle/wake,
   night mode and touch coordinates. Measure kiosk RAM and touch responsiveness.

If a WebView replacement is required, it is a **separate system-write phase**:
verify the stock system/tree backup, SDK/ABI, free space and all native libraries;
stage/read back the replacement; preserve the original APK and odex tree; then
approve the switch. Package version alone does not prove the renderer loads.
Prefer reversible application-level alternatives if they meet the RAM budget.

Do not alter zRAM, flash Android, add CA roots or change device timezone unless a
measured requirement independently justifies and approves that change.

## 5. Permanent kiosk and network deployment

Only after the USB test passes:

- Choose a stable frame IP and the server interface explicitly; reserve addressing
  carefully because some variants randomize their Wi-Fi MAC at each boot.
- Deploy a reviewed user service for the Python backend, bound to that LAN interface
  with `--allow <frame-ip>`. Add a firewall rule limited to this frame. No Internet
  port forwarding and no public proxy route.
- If using a shared LAN instead of a truly isolated segment, implement device
  authentication before deployment; the current IP allowlist is not sufficient.
- Preserve Home Assistant's private bridge and loopback-only UI.
- Configure the kiosk as a Home app if the firmware's BOOT_COMPLETED delivery is
  restricted; a boot receiver alone may not autostart on these units.
- Coordinate the native maintenance gesture with the UI's three-second two-finger
  hold. The upstream kiosk uses 1.5 seconds; do not ship competing gestures silently.
  Always retain a tested recovery/launcher path.
- For a matching AiMOR device, disable the identified vendor launcher/updater/test
  packages only after the fallback is working and this phase is approved. Wait for
  package-state persistence before power cycling; verify disabled state and lack
  of TCP-7806 activity after reboot.
- Verify boot-to-dashboard, screen-on behavior and actual brightness scheduling.
  The web UI's dark night view does not control hardware brightness.

The dashboard remains sample-data software until the separate adapters are built.
Installing the display does not make calendar/weather/Aura/HA integrations real.

## 6. Rollback and acceptance

Record original launcher/defaults, installed packages, display settings and every
changed system file before writes. If rendering fails, restore the original WebView
whole tree if changed; return to the tested fallback Home app before uninstalling
the kiosk. Remove ADB reverse mapping, backend unit and narrowly added firewall rule
when undoing deployment. Do not re-enable the vendor connection on an unprotected
network. Flash rollback must use the reviewed, matching route.

Acceptance is on the actual frame: cold boot, power-cycle recovery, all view/touch
checks, persistent shopping, no browser secrets/external requests, RAM/temperature,
Wi-Fi outage, server outage, idle/wake and a multi-day soak. Installation success
messages or host Chromium tests are not frame acceptance.

## References / freshness

Read the original handoff's pinned `9dd323e` guides and current upstream README,
start-here guide and relevant recent PRs on 2026-10-12. Current upstream documents
additional January/April/May variants; the original January-only assumption must
not determine the route. PR #45 (April Route S report) and PR #14 (macOS helpers)
were open/unmerged when checked; they are not approved installation inputs.

- https://github.com/wesbos/photo-frame-dashboard/blob/main/docs/pf1007l-start-here.md
- https://github.com/wesbos/photo-frame-dashboard/blob/main/docs/aimor-remote-root-shell.md
- https://github.com/wesbos/photo-frame-dashboard/blob/main/docs/allwinner-a33-pf1007l.md
- https://github.com/wesbos/photo-frame-dashboard/pull/45
- https://github.com/wesbos/photo-frame-dashboard/pull/14

**Resume input needed:** About model/full firmware, ports, whether a known A-to-C
**data** cable is attached directly and the frame is powered, and (only for network
fallback) confirmed TCP-7806 isolation plus the owner's positively identified frame IP.


### Kiosk v0.5 browser update

Adds an unexported single-tab BrowserActivity using the installed WebView, native
address/search/history controls and a Read recipe result back to the dashboard.
No new runtime engine, permissions, public server route or network admission.
Update uses `adb -d install -r kiosk/build/home-hub-kiosk.apk` after source review
and signed build verification. A private copy of the installed predecessor APK is
retained under the owner state directory; never commit that binary or pairing data.
Hardware acceptance must verify launch, web page loading, cancellation/back,
Read recipe import/focus, and normal dashboard restoration with existing pairing.
