# Warm display and embedded browser

The dashboard uses a warm ivory background, cream cards, terracotta actions,
muted sage status colors and the existing bundled Atkinson/Fraunces fonts. No
new frontend framework, raster UI backgrounds or external font requests were added.
The 1280×800 stage uses a 232px sidebar with nine navigation items.

## Design comparison

Today and Recipes were implemented against generated 16:10 concept references.
Synthetic rendered screenshots were inspected at 1280×800 for Today, Calendar,
Smart Home, Settings and Recipes. Comparison ledger:

- Palette: matched the concept's ivory/cream/terracotta hierarchy; omitted image
  grain so the interface stays flat and inexpensive to render.
- Navigation: standardized both concepts to a 232px sidebar with 56px touch rows;
  retained all nine existing destinations and added a simple Home Hub wordmark.
- Today hierarchy: matched the large clock, separate weather card, paired next-up
  and shopping cards, and centered serif quotation. Actual alerts retain their
  top banner, which shifts content below the concept's ideal empty state.
- Recipes: matched header actions, Saved/Find/Recent tabs, full-width search and
  three-column text cards. Real catalog contents determine card count and text;
  no sample recipes or fabricated duration labels are installed into live data.
- Typography: retained bundled accessible fonts and adapted the concept's sizes
  to the physical tablet. No network font cost was introduced.
- Overflow: cards/settings remain scrollable; browser tests cover the landscape
  stage, scaled viewports, reader focus mode, and saved editor drafts.

## Kiosk 0.6

BrowserPanel is a second transient WebView inside MainActivity, positioned to the
right of the sidebar. Close browser or any other sidebar destination destroys it.
Android Back traverses browser history before closing the panel. Read recipe
validates the current public HTTPS URL and returns to the dashboard reader.
The public WebView has no JavaScript bridge. The dashboard alone can invoke the
small trusted-origin action set for browsing, closing and window brightness.
Existing public URL policy, default TLS validation, blocked file/content access,
popup prohibition and disabled disk cache/third-party cookies remain in force.
These hostname checks do not provide DNS rebinding isolation.

Settings → Display exposes a 10–100% brightness slider only after the native kiosk
reports its capability. The percentage persists in private Android preferences.
It changes this app window, not the system brightness setting, and needs no new
permission. A 10% lower bound prevents accidentally blacking out the tablet.

The APK update preserves pairing, preferences and IndexedDB. Signing inputs and
APKs remain outside the Git index; runtime photos and credentials are never
published. The old standalone BrowserActivity has been removed.

## Acceptance — 2026-10-18

On the actual tablet, v0.6 kept MainActivity active while the embedded browser
created its second WebView. The sidebar measured 232px; selecting Recipes disposed
the second WebView and showed the native catalog. Brightness55% produced Android's
140/255 window override and persisted across an APK update. The tablet photo cache
still held300 images plus thumbnails, totaling46847388 bytes.

The owner disconnected USB after deployment. Keyboard resizing, browser history
and Read recipe's updated native callback have static review but still need their
final physical-device check; no full reboot or extended soak is claimed.

Tapo: Deco listed only the two existing C110 cameras. Bounded unauthenticated
TP-Link discovery on the upstream subnet returned no additional devices. The
upstream Archer router login is prepared for owner-local authentication; no
credential guessing, factory reset or custom integration was performed.
