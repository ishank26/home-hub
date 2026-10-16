# Home Hub requirements v1.1 (draft, 12 Oct 2026)

These are changes against the owner's v1.0 (`~/Downloads/Humblestead_Home_Hub_Feature_Requirements.docx`),
which stays authoritative for anything not mentioned here. Tags:
- **Confirmed**: already in v1.0, or decided by the owner.
- **Changed**: differs from v1.0.
- **New**: not in v1.0.

Target: a 10.1-inch landscape frame (1280 × 800) on a kitchen wall, read from 1–3 m by the whole
family, running a custom web UI on an older Android WebView. Data and credentials stay on the home server.

## 1. Legibility and touch
- **Changed**: touch targets are at least 56 × 56 px (v1.0 said 44), because hands in a kitchen are often wet or busy. Whole list rows are tappable.
- **New**: type floor. The clock is at least 96 px, key values at least 28 px, body text at least 20 px, and nothing is below 16 px.
- **New**: contrast is at least 4.5:1 for text and 3:1 for icons and borders. No light-grey secondary text. Tinted chips carry dark text.
- **Confirmed**: charcoal on warm white, one restrained blue accent, no unneeded animation.

## 2. Navigation
- **Confirmed**: a fixed left sidebar, 180 px wide, icon plus short label, in this exact order on every screen: Today, Calendar, Shopping, Weather, Quotes, Photos, Smart Home, Settings. Each entry appears exactly once.
- **Changed**: Quotes and Photos are separate views (the first mockup merged them).
- **New**: the sidebar footer shows overall sync health; tapping it opens Settings.
- **New**: after 2 minutes idle on any tab, return to Today before the screensaver starts.

## 3. Screensaver, wake and night
- **Confirmed**: after 3 minutes idle, show a full-bleed Aura photo. Swiping up wakes to Today; there is no passcode.
- **Changed**: change the photo every 30 s (v1.0 proposed 15 s).
- **New**: the clock sits on a soft scrim at the bottom, with no page dots. The clock drifts a few pixels each minute to prevent burn-in.
- **New**: a tap shows "Swipe up to open" for 3 s; it never changes tabs.
- **Changed**: night mode during quiet hours (default 22:00–06:00) shows a dark clock at low brightness and the next morning item, with no photos.

## 4. Alert strip (global, new)
- A single line at the top of the main area, hidden when there is nothing to show. The highest severity goes first. Show at most one line, with "+n more" for the rest.
- Sources come only from the server's allowlist: a door contact open longer than [N] min, a weather alert, a sync failure, or Home Assistant offline.
- Tapping it opens the relevant tab. It replaces the optional smart-home status line on Today.
- It never shows camera images or the content of personal messages.

## 5. Today
- **Confirmed**: large clock and date, compact weather, the next 2–4 events, a shopping preview and one quote. No vertical scroll.
- **New**: events show a relative time ("Now", "in 25 min") and their calendar color.
- **New**: the weather tile shows the next rain window ("Rain from 3 PM · 60%").
- **Changed**: the quote is a one-line footer rather than a hero card.
- **Confirmed**: shopping shows the open count plus up to 3 items.

## 6. Calendar
- **Changed**: the default view is 3-day. Day, Week and Month stay available.
- **Confirmed**: a current-time line, an all-day row, a Today button, previous/next and a date picker.
- **New**: the legend is the filter. Each calendar is a toggle chip in its color, and the colors differ in lightness as well as hue.
- **New**: overlapping events sit side by side. The visible window is 7 AM–6 PM, scrolling for other hours. Tapping an event opens a read-only detail.

## 7. Shopping
- **Confirmed**:
  - categories Produce, Dairy, Pantry, Household, Other;
  - quantity and notes;
  - large checkboxes;
  - Undo on delete.
- **New**: quick-add chips for frequent items.
- **New**: completed items collapse into one group with "Clear completed".
- **Confirmed**: each item shows its sync state: "Saving…", or "Not saved · Retry" on failure. Never show a false success.

## 8. Weather
- **Confirmed**: observed current conditions are labelled separately from forecast values, with the source and update time.
- **Confirmed**: an hourly strip with chance of rain, and 7-day cards with chance of rain or snow.
- **Changed**: rain and temperature lead; detail metrics (wind, humidity, UV, sunrise and sunset) move to a secondary grid.
- **Confirmed**: fields the provider omits are left out, not filled with placeholders.

## 9. Smart Home: real devices only
- **Changed**: no thermostat, smart lock or garage door, because none is in the inventory.
- **New**: the order is door contacts (T110), then scenes (Good Morning, Movie Night, All Off), then light tiles (Govee H6008, Twinkly), then cameras.
- **Confirmed**: camera snapshots refresh every 30–60 s, with at most one live view, opened on tap. The D205 doorbell shows "pending verification" until its integration is confirmed.
- **New**: a command shows "Sending…" and then the state Home Assistant confirmed, with a 5 s Undo.

## 10. Frame performance (WebView ~106, ~1 GB)
- **New**: no live `backdrop-filter` blur. If a blurred photo is needed, the server pre-renders it.
- **New**: fonts are self-hosted, at most two families and three weights. The frame makes no web-font calls.
- **Confirmed**: only one view is mounted at a time; hidden views unmount. Photos use server-made thumbnails and display copies.
- **New**: at most one shadow per card, crossfades only, and a 200 KB JS budget (gzipped).

## 11. Architecture and privacy
- **New**: a dedicated dashboard backend on the home server holds a scoped Home Assistant token and the Aura secrets. The frame never talks to Home Assistant directly. Home Assistant keeps its private bridge and loopback-only UI.
- **New**: camera snapshots and doorbell events stay in this backend and never enter the Hermes assistant.
- **Confirmed**: no password or token appears in a URL, the JS bundle, logs, or any response sent to the frame.

## 12. Settings and honest states
- **Confirmed**: sync status for each source with its last success; display, screensaver and quiet-hours settings; diagnostics; an admin path.
- **New**: each source has three visible states: current, stale (amber, with its age) and failed (with Retry). Stale data is never shown as live.
- **New**: admin mode needs the two-finger hold from v1.0 §4.3; a single tap never opens it.

## Decisions in this draft
- Wake always lands on Today.
- The screensaver starts after 3 min, and the photo changes every 30 s.
- Night mode is a dark, dim clock rather than screen-off, because the frame is also the kitchen clock.
- Shopping uses a Home Assistant to-do list as its source, so the family can also edit it from the HA phone app.

## Still open
- Calendar source resolved 2026-10-15: owner selected iCloud through HA CalDAV;
  HA authentication is complete; dashboard access is deferred pending its HA credential.
- The door-alert threshold [N] min, and which doors trigger it.
- Calendar names and colors for each family member.
- Home location, units and quote categories.
- Frame identity resolved: PF1007L April 20260410 firmware, WebView 106.
- Photos selected 2026-10-15: mirror one existing Aura frame, with iPhone uploads
  through the official Aura app. The read-only mirror is implemented; local Aura
  authentication and first live sync remain pending.
