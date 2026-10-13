# Home Hub design: mocks in this repo

Everything an implementer needs is in this folder; no external link is required.

- `requirements-v1.1.md`: the revised requirements (supersedes v1.0 where tagged).
- `mocks/*.dc.html`: the source of each mock screen, one file per 1280 × 800 artboard. Each file is
  plain HTML with **inline styles**: read it for exact sizes, colors and copy.
  - Repeated content comes from `renderVals()` in the `<script type="text/x-dc">` block at the bottom.
  - `{{name}}` marks a value filled from there; `<sc-for>` repeats; `<sc-if>` is a condition.
  - `<dc-import name="Sidebar">` embeds `Sidebar.dc.html`.
  - The files need a design-canvas runtime to render, so **do not open them expecting a page**.
- `mocks/canvas.json`: board titles and their layout on the original canvas.
- The original interactive canvas (private, owner-only): https://claude.ai/artifact/6ifw6WadCvNHLEYQ6gHqUj.

`static/app.css` already implements these tokens and component styles. Build views against its
class names; the per-screen notes below say which.

## Tokens

| Token | Value | Use |
|---|---|---|
| ground | `#FBFAF7` | page background (warm white) |
| panel | `#FFFFFF` | cards, with border `#E6E2D9`, radius 20 px |
| rail | `#F3F1EC` | sidebar background, right border `#E3DFD6` |
| ink / ink-2 / ink-3 | `#1F2328` / `#2F3640` / `#4A5058` | text; ink-3 is the lightest allowed on white |
| accent | `#1F5FD1` | active nav, primary buttons, selected state (white text) |
| ok / warn | `#15803D` dot; `#FCE9D9` background with `#5C2805` text | sync health, open-door alert |
| rain | `#1E4E8C` | chance of rain everywhere |
| now line | `#B42318` | calendar current time |
| calendar colors (dot / chip bg / chip text) | Family `#2F6FD6` `#DDE8FA` `#143E8C` · Work `#C2570C` `#FBE3D2` `#6A2E06` · School `#0F7B6C` `#D8EFEA` `#0B4A41` · Sports `#7A4CC2` `#EBE1F8` `#46237A` | they differ in lightness as well as hue |
| body font | Atkinson Hyperlegible 400/700 | everything except quotes |
| quote font | Fraunces italic 400 | quotes only |
| type scale | 16 / 17–19 / 20–23 / 26–32 / 44–60 / 96–132 / 220 (night) px | the floor is 16 px |
| tap target | 56 px minimum; nav items 60 px; list rows 58–64 px | |

## Shared frame
- The stage is 1280 × 800. The sidebar is 180 px (`.rail`); the main area is 1100 px with 22–24 px top
  and 32 px side padding (`#main`).
- Sidebar (`Sidebar.dc.html`):
  - eight items, each a 26 px stroke icon plus a 19 px bold label, in the order Today, Calendar,
    Shopping, Weather, Quotes, Photos, Smart Home, Settings;
  - the active item is filled with the accent and has `aria-current="page"`;
  - a flexible spacer, then a sync footer: a dot plus "All synced · 7:41", or an amber "Photos stale · 2 h". Tapping the footer opens Settings.
- The alert strip (`.alert`) is 56 px tall, warn colors, at the top of `#main`: icon, then "**Back door is open** · 12 min", then "View".

## Screens

### Screensaver (`Screensaver.dc.html`)
- A full-bleed photo (cover crop). A bottom scrim 320 px tall fades from rgba(10,14,16,.78) to transparent.
- Clock at bottom-left (64 px from the left, 56 px from the bottom): "7:42" at 132 px bold, and below it
  "Thursday, October 10 · 62° Clear" at 30 px.
- The tap hint sits bottom-right: a pill with an up arrow and "Swipe up to open", 22 px.
- There are no page dots and no sidebar.

### Today (`Today.dc.html`)
1. The alert strip, only when an alert exists.
2. Top row, aligned to the bottom edge:
   - Left: clock "7:42" at 120 px plus "AM" at 36 px, with the date at 30 px below.
   - Right: a weather tile at least 360 px wide with a 64 px sun icon, "62°" at 52 px, "Clear · H 72° L 54°"
     at 19 px, and "Rain from 3 PM · 60%" at 19 px bold in the rain color. Tapping it opens Weather.
3. Grid at 1.6fr : 1fr:
   - **Next up** card:
     - Header "Next up", with "Calendar ›" on the right.
     - 4 rows, each 64 px with a top divider: a 14 px calendar dot, the time at 21 px bold in a 112 px column, the title at 23 px with the calendar name at 16 px below, and a relative pill on the right ("in 18 min" filled with the accent when it is the next event; otherwise neutral).
   - **Shopping** card, all tappable: "8 open items" with the number at 44 px, 3 rows (name at 22 px, quantity at 18 px in ink-3), then "+ 5 more".
4. Footer quote line: "“Well done is better than well said.”" in Fraunces italic at 24 px, then "Benjamin Franklin" at 18 px. Tapping it opens Quotes.

### Calendar (`Calendar.dc.html`), 3-day default
- Header row:
  - "Calendar" at 32 px;
  - the range "Thu Oct 10 – Sat Oct 12" at 22 px;
  - a segmented control Day / **3 Day** / Week / Month (`.seg`);
  - ‹ and › buttons (56 px) with a "Today" button between them.
- Legend chips are filter toggles (`aria-pressed`). Off renders white with a grey border and grey text; the
  mock shows Work off, so the work standup is hidden.
- Day header row: a 64 px time gutter, then 3 columns. Each shows the weekday at 20 px bold and the date; today's date sits in a
  38 px accent circle. All-day chips appear under the header ("No school", "Grandma visiting").
- Time grid: 7 AM–5 PM visible at 50 px per hour, with hour labels at 16 px and hairlines in `#EFECE5`.
  - Today's column has the background `#F4F7FD`.
  - Events are tinted chips: title at 18 px bold, time at 16 px.
  - Overlapping events split the column width (Fri: Dentist 9–10 next to School concert 9:30–10:30).
  - The now line is 3 px in red at the current time, today's column only.
- Week view: the same grid with 7 columns. Month view: a 7-column grid of cells holding the day number and up to 3 event lines.

### Shopping (`Shopping.dc.html`)
- Header: "Shopping", then "8 open · Synced 7:40" with "Synced" in bold green.
- Add row: a text input 60 px tall (22 px text, 2 px border `#C9C4B8`) and an "Add" primary button. The live
  build adds a category select between them.
- Quick-add chips: "+ Bread", "+ Yogurt", "+ Apples", "+ Dish soap".
- Two columns of category cards (Produce and Dairy | Pantry and Household). Each card has an uppercase 18 px heading, then rows
  58 px tall: a 30–32 px checkbox, the name at 22 px, the quantity at 18 px, and an optional "Saving…" warn pill.
- Completed bar at the bottom (`#F1EFE9`): "Completed (1)", the struck-through names, and a "Clear completed" button.

### Weather (`Weather.dc.html`)
- Header: "Weather", "[Home location]", then on the right "Observed 7:35 AM · Forecast 7:30 AM · [Provider]" at 17 px.
- Top grid at 1fr : 1.25fr:
  - Hero card: a 96 px icon, then "NOW · OBSERVED" at 16 px caps, "62°" at 96 px, "Clear · feels like 60°" at 22 px, and "Today H 72° · L 54°".
  - Detail card, 3 × 2: label at 17 px with the value at 30 px bold. Items: rain today "60% · 3 PM" (rain color), wind, humidity, UV, sunrise, sunset.
- "Next hours" card: 8 slots showing the hour, an icon (sun, cloud or rain), the temperature at 24 px and the rain % at 16 px. Slots at 50% chance or more get the background `#E6EEF9`.
- 7 day cards: day, icon, condition, high at 26 px bold with the low in ink-3, and "NN% rain". Today's card is highlighted with `#F4F7FD` and the border `#B9CCF0`.

### Quotes (`Quotes.dc.html`)
- "Quotes" plus "Today’s quote · changes daily".
- A large card (`#F3EEE4`, radius 28) holding a quote-mark icon, the quote in Fraunces italic at 60 px, the author at 26 px bold and the source at 19 px.
- Buttons "Save" (heart, `aria-pressed`) and "Next quote" (primary).
- Use only quotes with verified attribution (the list is in `server.py`).

### Photos (`Photos.dc.html`)
- "Photos", then "From your Aura frame · synced 7:30 AM", then a "▶ Start slideshow" primary button.
- Collection chips (All, Family, Trips, Seasonal); the selected one is filled in ink.
- A 4-column grid with 14 px gaps of rounded photo buttons, 16 px radius. Tapping one opens the fullscreen viewer with previous/next.

### Smart Home (`SmartHome.dc.html`)
- "Smart Home", then "Home Assistant connected" in green.
- Contact chips: "Front door Closed", "Back door Open · 12 min" (warn), "Patio door Closed", then "Tapo H100 hub online".
- Three scene buttons, each 76 px tall at 23 px bold: Good Morning and Movie Night in the accent, All Off in ink.
- Four light tiles, each 128 px tall: a bulb icon and "On"/"Off" at top, then the name at 21 px bold and the detail at 16 px. On is `#FFF6DE` with the border `#E8C766`.
- Cameras: 2 snapshot tiles showing the name, the snapshot age and a "View live" button, then a dashed "Doorbell (D205)" tile reading "Pending verification".
- Toast: dark, bottom-center, showing "<name> · confirmed by Home Assistant" with an "Undo" button.

### Settings (`Settings.dc.html`)
- Two cards.
  - **Sync status** rows, each 76 px tall: a dot, the name, a note, and "Refresh" or "Retry". The stale example is Aura photos, amber: "Stale · last success 5:30 AM (2 h). Showing cached photos." with a primary Retry.
  - **Display & screensaver**: clock 12 h/24 h; °F/°C; "Screensaver after – 3 min +"; "New photo every – 30 s +"; "Quiet hours 10:00 PM – 6:00 AM · Dark clock".
- Diagnostics bar: "WebView [version] · 1280 × 800 · storage [free] · last error none" and "Admin: hold two fingers for 3 s".

### Night (`Night.dc.html`)
- Background `#0B0C0E` with text `#9C958A` and no sidebar.
- Centered: the clock at 220 px, the date and temperature at 32 px, and a pill "Tomorrow 9:00 AM · Dentist".
- An optional alert pill at the top (`#2A1A0E` background, `#E2A36B` text). Footer at 18 px in `#8C867C`: "Quiet hours until 6:00 AM · tap to brighten".

## Sample content
The names, events, doors, rooms and numbers in the mocks are placeholders. Values in `[brackets]` are
unknowns for the owner to supply. Real values come from the adapters (see `HANDOFF.md`, Phase 2 and Phase 4).
