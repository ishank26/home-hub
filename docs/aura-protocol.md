# Aura photo mirror: protocol evidence and operation

Implemented 2026-10-15. This is an unofficial, independently implemented,
read-only client. It does not register a simulated Aura frame or alter an existing
frame. Aura may change its private protocol; authenticated live acceptance is
still required after the owner signs in.

## Evidence inspected

- Public source [zmanowar/auraframes](https://github.com/zmanowar/auraframes), pinned
  at `4a4a0f36e85222ed1e37ad8b9047f49d4f34ded3`: `accountApi.py`, `frameApi.py`,
  `client.py`, `export.py`, asset/user models and settings.
- Independent [2026 protocol example](https://gist.github.com/kboenke/51110fb2f66b65989f999e2a4e23207e)
  confirms v5 login/user headers and assets. Its destructive operations are not
  implemented or executed.
- The vendor's public [web login](https://app.auraframes.com/login) and referenced
  public web-client bundle were inspected without signing into an account. The
  public bundle did not expose the mobile API methods; it is not treated as
  authenticated protocol proof.
- A credential-free GET to `https://api.pushd.com/v5/frames.json` returned HTTP400
  with `Missing or invalid X-User-Id`, confirming that the current endpoint
  enforces that authentication header. No account enumeration was performed.

No third-party client was installed, imported or executed. The inspected Python
client logs complete request/response objects, including authentication data,
and includes unrelated upload/delete/control operations. This implementation
uses a closed request set and sanitized errors instead.

## Implemented operations

| Operation | Protocol |
|---|---|
| Login | POST `https://api.pushd.com/v5/login.json`, nested `user.email/password`, locale and locally generated client/device identifier |
| Session | Login `result.current_user.id/auth_token`; subsequent API requests use `X-User-Id` and `X-Token-Auth` |
| Frame selection | GET `/v5/frames.json`; owner selects exactly one accessible frame in the local terminal |
| Photo enumeration | GET `/v5/frames/<id>/assets.json?limit=100&cursor=...`, advancing `next_page_cursor` |
| Image retrieval | Credential-free HTTPS GET to `imgproxy.pushd.com`; prefer returned landscape rendition, otherwise encoded user/file path |

Only login can POST. Other HTTP write methods and unrecognized API routes are
refused. TLS verification stays enabled; proxies and redirects are disabled.
Image requests never contain the account token. API/image response sizes,
pagination, cache growth, image dimensions and process resources are bounded.

## Photo handling and failures

`aura_sync.py` runs separately from the standard-library HTTP server. It polls
every fifteen minutes after setup, deduplicates stable asset/revision IDs,
excludes known unselected/hidden entries and videos, and uses the still image for
Live Photos. Unsupported image formats fail the snapshot safely.

Pillow12.3.0 applies EXIF orientation, resizes to fit1280×800 and400×250, then
writes new JPEGs without EXIF/GPS/XMP/ICC/comments. Originals and raw API responses
are not saved. Remote user IDs, original filenames, image URLs and location fields
are never in the public manifest. Public IDs are opaque hashes.

A manifest is replaced atomically only when the entire snapshot is ready.
Failures keep the last published manifest and mark its photos stale. New files
from a failed attempt are rolled back. Old unused generated files are pruned
after24hours; the cache is capped at512MiB/4000files, with128MiB minimum free disk.
The worker has512MiB memory,50%CPU and a12minute process limit. These are resource
bounds, not promises about completion time for a large initial collection.

The server serves only IDs in the current published manifest through its existing
frame admission checks. Thumbnails are used in the grid; display JPEGs are used
in the viewer/screensaver. The screensaver refreshes its manifest every minute,
labels stale photos, tolerates failed loads and clears removed/empty collections.

## Connect the existing Aura account

The runtime and user timer templates are installed on this host. The timer stays
disabled until a complete first login/selection/sync succeeds. Run locally:

```sh
cd ~/work/home-hub
scripts/aura-setup
```

Enter the Aura account email and Aura password at the terminal prompts, then
choose the source frame number. Password input is hidden. Only the resulting
session token, user ID and selected frame ID are saved in the private0600
`~/.config/home-hub/aura-session.json`; the password is not saved. The helper then
restarts the dashboard and enables `home-hub-aura.timer`. Do not send credentials
in chat. If login requires an unsupported challenge, stop and inspect the
official flow rather than bypassing it.

To reinstall the pinned runtime/unit templates: `scripts/install-aura-runtime`.
The install uses an official PyPI binary wheel with a pinned SHA-256 in
`requirements-aura.txt`, and requires this host's CPython3.13/x86_64 environment.

```sh
systemctl --user status home-hub-aura.timer
systemctl --user start home-hub-aura.service  # bounded immediate refresh
systemctl --user disable --now home-hub-aura.timer  # stop future polling
systemctl --user stop home-hub-aura.service         # stop a current refresh
```

Stopping the worker retains the local photo cache. To switch back to sample photos,
remove the `photos` block from private config and restart `home-hub.service`.
No Aura cloud content is removed by either operation.

## Adding photos from an iPhone

Use the official Aura iPhone app to add photos to the selected existing Aura frame.
This mirror then picks them up on its next successful sync. That is the supported
iPhone → Aura → Home Hub path; direct iCloud Photos account sync is not implemented.
See [Aura's photo upload explanation](https://help.auraframes.com/hc/en-us/articles/360049921814-My-app-or-frame-doesn-t-show-all-photos-or-videos).

## Verification and remaining acceptance

Synthetic API tests cover closed operations, auth isolation, proxy/redirect
restrictions, pagination loops, malformed responses and byte limits. Real JPEG
tests cover orientation, metadata removal, resizing, deduplication, rollback,
stale caches and cache limits. HTTP tests exercise manifest/image/thumb routes and
unpublished IDs. Desktop Chromium exercises thumbnail/full-size decoding,
screensaver additions/removals, stale labels and empty-cache clearing without
external browser requests.

No live Aura account has been authenticated and no personal photos have been
downloaded. First live setup must verify frame membership, image-proxy URL shapes,
pagination, photo inclusion/exclusion and an upload through the official app.
Native frame reboot/soak and encrypted/isolated LAN transport remain separate
acceptance items. Current HTTP frame admission does not encrypt LAN traffic.
