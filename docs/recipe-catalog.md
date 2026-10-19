# Persistent recipe catalog

The Recipes screen stores private recipe text on the dashboard server. It supports
manual creation, public structured-recipe imports, explicit Save, title/tag search,
editing and confirmed deletion. Saved recipes are never evicted by newer imports.
The catalog allows 200 saved recipes and five rotating unsaved previews. A stable
reader link loads stored content without fetching the publisher; the dashboard
server must remain reachable.

Data lives in the configured runtime directory's recipes.json, outside Git.
Existing records from the former recent-five reader become saved recipes without
changing IDs or truncating text. Larger legacy records remain readable/editable.
New recipes are bounded to 24 KiB; legacy recipes to 3 MiB; the catalog to 20 MiB.
Only authenticated PATCH requests for an existing legacy record receive the larger
request-body allowance. Lists return metadata, not ingredients, steps or notes.

Writes use the existing global writer lock and atomic private-file replacement.
Edit/save/delete requests require a matching revision; stale mutations return409.
A missing record returns404. Malformed persisted data blocks mutations with503,
preserving the original rather than replacing it with an empty catalog. Reimporting
a source returns the existing record without overwriting personal edits. Manual
creation with a duplicate source reports a conflict. Draft editors are protected
from periodic refresh and automatic idle navigation. Successful mutations update
the UI immediately even if an optional following list refresh fails.

Recipe Tracker opens a verified local copy of the owner's published demo app.
The external site failed to navigate in the old tablet WebView, so its three public
build assets (543743 bytes total) are hash-pinned and installed outside Git. They
are served under the existing admission boundary with a strict content security
policy blocking network/provider calls, frames, workers and form submissions.
A local cryptographic UUID compatibility shim supports the tablet's HTTP LAN
origin, and a Back to dashboard link returns to Home Hub. This reviewed owner
bundle shares the dashboard origin; CSP is defense in depth, not origin isolation.
Its browser-local library does not automatically synchronize with the dashboard's
server catalog. Private source, provider keys and databases are not copied into
this repository.

Quotes are shown automatically on Today and rotate daily. The standalone Quotes
navigation, actions and API endpoint have been removed.

## Verification — 2026-10-18

Independent review approved after fixing draft refresh, legacy compatibility and
post-mutation refresh failure handling.113 backend tests passed. Recipe browser
QA passed public import/save, manual CRUD, reload persistence, stable reader links,
filtering, escaped text, concurrent-edit conflict,181-second draft preservation,
and successful PATCH/DELETE with a failed subsequent list GET. General UI checks
passed eight navigation entries, homepage quote, shopping, stale-source fallback,
idle, night and saver behavior. Browser plugin was unavailable; existing regular
Playwright runtime tested1280×800 and390×844 viewports. Mobile catalog retains the
app's scaled landscape layout; focus reader adapts to the narrow viewport.

The live service was restarted and the physical1280×800 tablet displayed the
catalog and a synthetic saved recipe in focus mode. Existing private recipes were
backed up outside Git before deployment. The synthetic record was removed after
verification, leaving the existing recipe intact. No device/server reboot or
extended soak was performed in this phase. Screenshots stay outside Git.


## Tablet photo storage

Only the current 300 normalized JPEGs and their thumbnails persist in WebView
IndexedDB, capped at256MiB. Streaming downloads have per-image size and time limits.
A single transaction replaces the complete sample; failed downloads retain the
old sample. Blob URLs are regenerated after reload and accepted only from the
cache module's owned URL set. Disable/empty-sample invalidation aborts streams,
invalidates in-flight reads/writes and removes persisted data, so disabled photos
cannot reappear on an offline reload. The photo server can be unavailable while
already-loaded dashboard pages show the stored copy. This does not guarantee that
the full app shell opens offline if the dashboard server is unavailable.


Latest owner override: the hourly reservoir and tablet cache now target up to300
photos, replacing the earlier10-photo policy. The worker downloads up to300 within
its600-second batch budget, under the existing512MiB server-cache limit. Tablet
cache failures/quota pressure retain the prior complete sample. Synthetic tests
exercise300 stored pairs. Aura is now authorized: the real hourly sample is300
photos, and actual tablet IndexedDB acceptance verified300 photos plus thumbnails
(46847388 bytes). The local
Recipe Tracker profile chooser rendered successfully on the actual tablet.


## Recipes navigation and fresh shell — 2026-10-18

The owner clarified that Recipes must stay inside the dashboard, so the default
sidebar route continues to display the local catalog. Recipe Tracker stays an
optional explicit launch button. The proposed direct sidebar redirect was removed
before publication. Existing recipeId/source reader links still work. Shell files
require cache revalidation on reload; API responses remain no-store.
