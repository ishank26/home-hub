# D205: Tapo Cameras Control

The built-in TP-Link integration failed to connect to this D205 even while its
HTTPS port was reachable. The community integration implements proprietary direct
streaming, which can work without RTSP/ONVIF. Upstream lists the D205 and reports
successful SD direct video. Doorbell-press events need separate physical testing;
UDP broadcast does not normally cross the existing router/container boundaries.
Do not change Home Assistant's private bridge or expose its web server to solve
that event discovery problem.

## Reviewed candidate

- Repository: https://github.com/JurajNyiri/HomeAssistant-Tapo-Control
- Release:7.2.8 (2026-10-12), minimum HA2026.9.0; installed HA2026.9.4 qualifies.
- Commit:057d7a8d0b47cbde283b77c19ca27bf4274b7594
- Source tarball SHA256:15f65f7fe26f82d6321fc1c73d5ab3b35c90601839554638245afe5f11957519
- Only28 component files (687544 bytes) are selected; no HACS installation needed.
- Declared dependencies:pytapo==3.4.26 and python-kasa[speedups]>=0.10.2. HA already
  pins python-kasa[speedups]==0.10.2. Pytapo source was downloaded from PyPI and its
  published SHA256 verified:69444bdc6585a7052e2bf380fb2563818df0b88ff3071b23d6266c03cdace2cc.
- The upstream manifest is preserved; HA manages normal PyPI dependency installation.
  Not all transitive dependency bytes are pinned by this installer.

Archive/source stay outside Git under the owner's private Home Hub review directory.
The installer accepts no credentials. Setup credentials stay in HA private storage.
The installer applies a reviewed local privacy patch: the shared component logger
suppresses detailed messages and tracebacks, and twelve setup exceptions are
replaced with constant messages without exception chains. This addresses observed
session-URL leakage in upstream failures. Installed file hashes record the patched
bytes. Keep debug logging disabled in HA/dependencies as an additional precaution.

## Owner-local installation

After independent review approves the exact installer:

```sh
sudo install -o root -g root -m 755 /home/ishank/work/home-hub/scripts/install-tapo-control.py /usr/local/sbin/home-hub-install-tapo
sudo /usr/local/sbin/home-hub-install-tapo
```

The first command installs an immutable root-owned program before execution. The
second checks existing Docker network/port/capability settings, verifies the source
hash, stages only regular component files, refuses to overwrite an existing Tapo
component, captures private pre-change boundary evidence, atomically publishes the
folder, and restarts HA. A failed HTTP readiness check moves the component into a
private rollback folder and requests another HA restart. No account/config database
is replaced. Existing camera integrations are preserved. The restart briefly pauses
HA devices/calendars. HTTP readiness alone does not prove component/device success.
Private installation records live under /var/lib/home-hub/tapo-install.

## Enrollment and acceptance

In HA → Settings → Devices & services → Add integration, select **Tapo: Cameras
Control** and the confirmed D205 address. Enter TP-Link credentials locally. Enable
Skip RTSP validation for this battery model. Keep recording/media synchronization,
thumbnail caching, show-on-map, time synchronization and motion/webhook handling
disabled for this enrollment. Keep camera privacy, recording, firmware and update
settings unchanged. Select the **SD Stream (Direct)** entity for initial viewing.
Keep the normal ten-minute battery polling interval; do not enable preload streams.

The dashboard accepts an optional camera configuration flag `onDemand: true`.
Such cards have no automatically refreshed thumbnail; tapping explicitly opens the
existing authenticated live viewer. Normal wired cameras retain their previews.
Do not add the D205 to the dashboard until authentication and stream acceptance pass.

Test one live viewer, then close it and verify its camera connection/FFmpeg producer
terminates and stays stopped. Upstream direct-stream restart callbacks have a
possible lifecycle race that needs live observation, especially for a battery
camera. Also test privacy-off/unavailable, reopened viewing, decoder cleanup and
bounded CPU/memory. Audio is disabled by the direct stream implementation. Doorbell
press/motion events are not promised by a successful video test.

Installation and device enrollment remain pending until the owner runs the sudo
steps. Tablet USB is disconnected; physical tablet viewing/reboot tests remain open.
