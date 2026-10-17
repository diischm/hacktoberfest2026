# BikeAble design

Frontend-owned. How the UI should look, and how to turn the design into the real app.

- **Mockup source:** [`mockup.html`](mockup.html) (exported from a Claude artifact). Open it in a
  browser; it runs standalone on its own mock data. Street tiles don't load in the mockup
  (it draws a sketched street grid instead); they do in the real app.
- **Screenshots:** [`screens/`](screens/), 390 × 844 viewport (phone), saved at 1×.
  Tall screens are full-page captures; the fixed top bar shows up mid-image in those
  (capture artifact, not a design choice).

Concept (from the mockup's header comment): *the city is a rider's scrapbook: every hazard
is a paper piece taped to the map.* A green cutting-mat board, paper/kraft/sticky-note
pieces, one signal-orange accent, handwritten display type, monospace receipts and tickets.
Single light look on purpose (paper is a physical material): **no dark variant.**

## Decisions

These override the mockup wherever they differ. Screenshots still show the mockup as drawn.

1. **Navigation:** keep the mockup's **top bar** (wordmark / brand) **and** the existing
   **bottom nav** (Map, Report, Routes) from `feat/web-skeleton`. The index-card menu (03)
   is a **stretch goal**, not built now.
2. **`/` is the map page.** The home collage's "Today on the map" receipt becomes a
   **small overlay card on the map**. The full collage is a **stretch goal** at `/about/`
   in `feat/pwa-polish`.
3. **Report detail sheet:** the feedback buttons (Still there / It's gone / Not accurate)
   sit in a **sticky action bar at the bottom of the sheet**, always visible on phones; the
   rest of the sheet scrolls above it.
4. **Contrast:** all five fixes in [Contrast](#mismatches-needs-decision) are
   **requirements for every frontend branch**, not suggestions.
5. **"Report here" button and the pick-location pin** use a **`--ink` background with
   `--paper` text/fill**, never accent orange, so only hazards look orange/red/amber on the map.
6. **Loader:** **max ~1 s**, **skipped** with `prefers-reduced-motion: reduce`, and
   **never blocks interaction** (no full-screen overlay waiting on data; the page renders
   and fills in as data arrives).

## Screen inventory

| Screenshot | Screen / state | Branch |
|---|---|---|
| [`01-loader.png`](screens/01-loader.png) | Intro loader: bike rides across a paper strip, rotating messages (first visit only) | `feat/pwa-polish` |
| [`02-home.png`](screens/02-home.png) | Home collage: hero note, scene, "Today on the map" receipt, checklist, best-route ticket (full page) | `feat/map-reports` (receipt from E3), `feat/route-compare` (ticket from E8/E9) |
| [`03-menu.png`](screens/03-menu.png) | Menu: index cards (Map, Report, Routes, Replay intro) over a blurred scrim | `feat/map-reports` (app shell) |
| [`04-map.png`](screens/04-map.png) | Hazard map: condition-colored pins, segments, Layers button, "Report here" FAB | `feat/map-reports` |
| [`05-map-layers.png`](screens/05-map-layers.png) | Layers panel (sticky note): filter by hazard type, lane condition, resolved | `feat/map-reports` |
| [`06-report-detail.png`](screens/06-report-detail.png) | Report detail bottom sheet: photo, chips, title, description, note, facts, feedback buttons | `feat/map-reports` |
| [`07-report-feedback-sent.png`](screens/07-report-feedback-sent.png) | Same sheet after "Still there": count bumped, button pressed, "Last seen just now" | `feat/report-feedback` |
| [`08-report-form.png`](screens/08-report-form.png) | Report form, empty: 1 photo, 2 tap the map, 3 note + "Send to the map" (full page) | `feat/upload-screen` |
| [`09-report-filled.png`](screens/09-report-filled.png) | Report form filled: photo preview "got it", pin + coordinates, note (full page) | `feat/upload-screen` |
| [`10-report-analyzing.png`](screens/10-report-analyzing.png) | Loading: "Reading your photo…" overlay, "up to 15 seconds" | `feat/upload-screen` |
| [`11-report-sent.png`](screens/11-report-sent.png) | Success: polaroid with "ON THE MAP" stamp, "See it on the map" / "Report another" | `feat/upload-screen` |
| [`12-report-rate-limited.png`](screens/12-report-rate-limited.png) | Error 429: button disabled, "You can retry in 60s" countdown | `feat/upload-screen` |
| [`13-routes.png`](screens/13-routes.png) | Route compare: scenario tabs, map with both routes, route tickets with score, RECOMMENDED stamp (full page) | `feat/route-compare` |

Not in the mockup (build them yourself, same style): an **empty** map state (no reports),
a **network/server error** state for the map and routes (the mockup only shows a toast),
and the 400/413/415 inline field errors (the mockup has the `.field-error` slot and the
logic, but no screenshot).

## Design tokens

Copied from the mockup's `:root`. The mockup writes colors in `oklch()`; hex is given here
(converted, same color) so the values are easy to read and compare. Token **names are
kept from the mockup** so its component CSS can be ported almost verbatim.

`feat/map-reports`: replace the placeholder token block in `web/static/web/css/app.css`
with this and update the few existing rules that use the old placeholder names
(`--color-ground` → `--board`, `--color-paper` → `--paper`, `--color-ink` → `--ink`,
`--color-ink-muted` → `--ink-soft`, `--color-accent` → `--accent`,
`--color-on-ground` → `--on-board`, `--fs-*` → `--text-*`, `--space-1…6` → `--space-2xs…2xl`,
`--shadow-card` → `--shadow-paper`).

```css
:root {
  color-scheme: light;

  /* the cutting mat (page background) */
  --board: #375C47;        /* oklch(44% 0.055 158) */
  --board-deep: #274836;   /* oklch(37% 0.05 158)  loader, top-bar gradient */
  --board-line: #486956;   /* 24px grid lines */
  --board-major: #537561;  /* 120px grid lines */

  /* paper stock */
  --paper: #F7F1E5;        /* cards, sheets, receipts */
  --paper-2: #ECE4D3;      /* photo/map placeholders */
  --kraft: #CEAE8C;        /* brown paper: hero note, report header */
  --kraft-deep: #BC9674;
  --sticky: #F7EA9B;       /* sticky notes: layers panel, routes header, hover */
  --lilac: #D9CDF1;        /* route ticket on home, "Replay intro" card */
  --tape: rgb(236 228 207 / 0.72);
  /* home scene illustration only */
  --sky-top: #82C1E2; --sky-low: #C1E6ED; --cloud: #EFF7FB;
  --mtn: #5E7791; --mtn-far: #849BB0; --grass: #5D9850;

  /* ink */
  --ink: #241B13;
  --ink-soft: #564B42;
  --rule: #C5BDB0;         /* dotted/dashed rules */
  --on-board: #E6F3E8;     /* text on the green board */

  /* the one accent: signal orange */
  --accent: #E65909;
  --accent-deep: #C33E00;
  --accent-ink: #FCF8F1;
  --focus: #DB4600;

  /* condition colors: fallbacks only, overwritten from GET /api/meta/ at startup:
     meta.conditions.forEach(c => root.style.setProperty(`--c-${c.key}`, c.hex)) */
  --c-green: #2E7D32;
  --c-amber: #F9A825;
  --c-red: #C62828;
  --c-grey: #757575;

  /* type: Google Fonts (see Translation notes), with fallbacks */
  --font-hand: "Gochi Hand", "Comic Neue", "Segoe Print", cursive;          /* titles, notes */
  --font-body: "Bricolage Grotesque", "Segoe UI", ui-sans-serif, sans-serif;
  --font-mono: "Space Mono", ui-monospace, "SFMono-Regular", monospace;   /* receipts, tickets, chips */

  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-md: 1rem;
  --text-lg: 1.25rem;
  --text-xl: 1.75rem;
  --text-2xl: 2.4rem;
  --text-display: clamp(2.6rem, 6vw, 4.6rem);

  --space-2xs: 4px;
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  --radius-sm: 4px;
  --radius-md: 10px;
  --radius-pill: 999px;

  --shadow-paper: 0 1px 0 rgb(35 50 38 / 0.25), 0 10px 22px -10px rgb(7 27 12 / 0.55);
  --shadow-lift: 0 2px 0 rgb(35 50 38 / 0.2), 0 22px 34px -14px rgb(4 22 8 / 0.6);

  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in: cubic-bezier(0.7, 0, 0.84, 0);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --dur-micro: 120ms;
  --dur-short: 220ms;
  --dur-long: 420ms;
  --dur-scene: 700ms;

  --topbar-h: 58px;        /* 64px from 761px up */
}
```

**Breakpoints.** The mockup is written desktop-first (`max-width: 980px / 760px / 560px`).
Our CSS is mobile-first, so write the same three steps as `min-width: 561px`, `761px`,
`981px`. At phone width (≤ 560px): one-column collage, top bar shows only the wordmark,
"Report a hazard" and the menu button, the legend is hidden, and report detail becomes a
bottom sheet.

**Background.** The board is `--board` plus two grid layers (24px and 120px lines) and a
fixed film-grain overlay (`body::after`, SVG noise, `mix-blend-mode: multiply`, 11 %
opacity). Copy both from the mockup's `body` rules.

**Motion.** Pieces "settle" in (drop + rotate, 80 ms stagger), tape animates on, pins drop.
`prefers-reduced-motion: reduce` collapses all of it to 150 ms; keep that block.

## Components

| Component | What it is | Seen in |
|---|---|---|
| Top bar | Fixed, gradient from `--board-deep`; wordmark (bike SVG + "BikeAble" in Gochi Hand). Brand only on phones; page links live in the bottom nav (Decision 1) | 02, 04 |
| Bottom nav | Existing from `feat/web-skeleton`: Map / Report / Routes, fixed, safe-area padding, `aria-current` on the active page. Restyle with the tokens (paper bar, mono labels, ink active state) | (not in mockup) |
| Menu (index cards) | **Stretch goal, not built now** (Decision 1). Full-screen scrim + 4 rotated cards with tab label, doodle, title, one line | 03 |
| Loader | Torn paper strip, bike riding across, mono message. **Max ~1 s, skipped with reduced motion, never blocks interaction** (Decision 6) | 01 |
| Map summary card | Small mini-receipt overlay on the map: "Today on the map" counts by condition + demo-data line, computed from E3 (Decision 2) | 02 (receipt) |
| Home collage | **Stretch goal** at `/about/` in `feat/pwa-polish` (Decision 2) | 02 |
| Paper pieces | `.piece` (rotated via `--r`), `.kraft`, `.sticky`, `.torn` (clip-path edge), `.tape` strips, `.sheet` | 02, 08, 13 |
| Receipt | Mono text, zigzag top/bottom edges, dotted leaders between label and number | 02 |
| Polaroid | Paper frame around a 4:3 photo + handwritten caption; "No photo" striped placeholder when `photo_url` is null or fails | 06, 09, 11 |
| Buttons | `.btn--ink` (dark pill), `.btn--line` (outline pill), `.btn--ticket` (accent, notched ticket edges, arrow), `.pill` / `.pill--paper` | 02, 08, 11 |
| "Report here" FAB | `.stamp-btn` with **`--ink` background, `--paper` text**, not accent (Decision 5) | 04 (shown orange in mockup) |
| Map pin | Teardrop in condition color with hazard icon; round for info types (`is_hazard: false`); dashed ring = `is_synthetic`; opacity = `freshness_weight` (min 0.55). **Icon in `--ink` on amber**, ink border on amber pins (Decision 4) | 04 |
| Segments | Leaflet lines in condition color; bike lane 6px solid, road dashed, informal path dotted; tooltip "name · score/100" | 04 |
| Layers panel | Sticky note with custom checkboxes: one per hazard type from meta, plus "Lane condition" and "Resolved reports" (`include_resolved`) | 05 |
| Legend | Mini receipt "KEY" with condition swatches from meta + "Dashed ring = demo data. Faded = older report." Hidden ≤ 760px | (desktop only) |
| Report detail | Polaroid; side card on desktop, **bottom sheet** (72 % height, rounded top) on phones; close button. Content scrolls, feedback bar stays pinned at the bottom (Decision 3) | 06 |
| Chips / badges | `.chip--cond` (condition color; **`--ink` text on amber and grey**, Decision 4), status label chip, `.chip--warn` dashed "Needs review", `.chip--demo` sticky-yellow "Demo data" | 06, 11 |
| Facts list | Mono `dt` + value: Reported / Last seen (time ago), AI sure (% or "Not analysed") | 06 |
| Feedback action bar | **Sticky bar at the bottom of the detail sheet**, always visible on phones (Decision 3): 3 boxes from `meta.feedback_actions`, big mono count + label; pressed = ink fill; optimistic bump, rolls back on error; 409 → "You already sent that" | 06, 07 (shown below the fold in mockup) |
| Upload form | Numbered steps (black circles): 1 drop zone / camera (polaroid), 2 pick map + coordinates (sheet), 3 lined-paper note with counter + ticket submit | 08, 09 |
| Pick pin | Teardrop marking the chosen spot: **`--ink` fill with a `--paper` dot**, not accent (Decision 5) | 09 (shown orange in mockup) |
| Analyzing overlay | Scrim + polaroid card with riding bike, rotating "Reading your photo…" lines | 10 |
| Result card | Polaroid with "ON THE MAP" rubber stamp, chips, description, two actions; needs_review text variant | 11 |
| Inline errors | `.field-error` (red, under each step), `.form-msg` (accent-deep, under submit), 429 countdown | 12 |
| Scenario tabs | Outline pills, selected = ink fill with sticky-yellow text (`role="tablist"`) | 13 |
| Route ticket | Paper ticket, left border in condition color, handwritten name, mono meta "KM · CONDITION · N HAZARDS", explanation list, perforated score stub "84 / 100", "RECOMMENDED" stamp | 13 |
| Toast | Ink bar bottom-center for non-field errors (load failures, truncated list) | (no screenshot) |

## Translation notes

The mockup is already **vanilla HTML/CSS/JS + Leaflet with no build step**, so almost all of
it ports directly. What has to change:

| In the mockup | In the real app |
|---|---|
| One page, four views switched on `location.hash` (`#home`, `#map`, `#report`, `#routes`) | Django pages per [WORKFLOW.md](../plan/WORKFLOW.md#frontend-plan) (`/`, `/report/`, `/routes/`), shared `base.html`. See Mismatches #1 and #2 |
| Its own `BikeAPI` object (`BikeAPI.meta()`, `feedback(report, action)`, `createReport({photo, lat, lng, note})`, `err.retryAfter`) | Our `web/static/web/js/api.js` (`getMeta()`, `sendFeedback(id, action)`, `createReport(formData)`, `err.retryAfterSeconds`). Don't copy `BikeAPI` |
| `window.BIKEABLE_MOCKS` inline mock data | `web/static/web/mock/*.json`. The mockup's mock set is richer (reports 104–109, segments 8–10, same shapes); copy those extra features into our mock files if useful |
| Leaflet 1.9.4 JS from unpkg + Leaflet CSS pasted inline | `<link>` + `<script>` for Leaflet 1.9.4 from unpkg (with SRI hashes), or vendor both into `web/static/web/vendor/leaflet/` so the demo works on bad Wi-Fi |
| Google Fonts `<link>` (Bricolage Grotesque, Gochi Hand, Space Mono) | Same `<link>` in `base.html` + `preconnect`; fallbacks are in the tokens |
| Colors in `oklch()` | Fine as-is (all current mobile browsers) or use the hex values above |
| Icons: inline SVG paths in a JS `ICONS` map keyed by `meta.icon`, bike drawing as SVG `<defs>` + `<use>` | Same: inline SVG, no icon library. Put the bike `<defs>` once in `base.html` |
| `.leaf` sketched street-grid background, `.mock-note`, hidden `csrfmiddlewaretoken` value `"mockup"` | Mockup-only: drop them. Real OSM tiles; real `{% csrf_token %}` / cookie |
| Collage drag + "Organize" (fine pointers only), "Replay intro" | Optional desktop delight; skip if short on time |
| Modern CSS/JS: `clip-path`, `mask`, `backdrop-filter`, `text-wrap: balance`, `100dvh`, `inert`, `structuredClone` | All supported in current Chrome/Safari/Firefox; no polyfills needed for the demo |

## Mismatches (needs decision)

**Contract (API_CONTRACT.md): none.** Checked:

- Condition colors: mockup fallbacks are exactly the `/api/meta/` hex values
  (`#2E7D32`, `#F9A825`, `#C62828`, `#757575`) and get overwritten from meta at startup.
- Every value shown comes from a contract field: hazard/status/condition labels from E2;
  description, note, photo, chips, Reported / Last seen / AI sure, feedback counts from the
  Report object; segment name/score/kind from E7; route name, `length_m` (shown as km),
  score, condition, explanation, `recommended_route_id` from E9. No reporter name, gallery,
  ETA or other invented field.
- Every action maps to an endpoint (E2–E9). Home receipt totals, layer filters by hazard
  type, and hazard counts on route tickets are computed client-side from E3/E9 data.
- Small note, no contract change needed: the route ticket's "N HAZARDS" looks up
  `hazards_on_route` ids in the loaded E3 list, so it can undercount if a report is outside
  the current bbox. Fetch missing ids with E4 or count `hazards_on_route` directly.

**Frontend decisions (no contract impact):** navigation, home vs map, and the report
detail layout are decided; see [Decisions](#decisions) 1–3.

**Contrast (WCAG AA): required fixes, see Decision 4.**

| Pair | Ratio | Where | Fix |
|---|---|---|---|
| Paper on amber `#F9A825` | **1.75** | `.chip--cond` text and pin icon for amber reports | Use `--ink` text/icon on amber (≈ 9:1), keep paper on red/green |
| Amber swatch/pin vs paper `#F7F1E5` / `#ECE4D3` | **1.75 / 1.56** | legend, receipt dots, amber pins on the map | Keep the dark `--ink` outline on swatches (legend has it, receipt doesn't); pins keep their paper border + shadow, add an ink border for amber |
| Paper on grey `#757575` | 4.10 | `.chip--cond` for grey (11px mono) | `--ink` text, or darken the chip only |
| `--accent-ink` on `--accent` | 3.42 | ticket submit (20px bold: passes as large text), **active `.pill--ink` (14px) and any other small-text accent button: fail** | Use `--accent-deep` (`#C33E00`) as the background for small-text accent buttons. ("Report here" FAB is `--ink`, Decision 5) |
| `--ink-soft` on `--kraft` | 4.05 | menu "Report" card description (14px) | Use `--ink` on kraft |

Also: the accent orange `#E65909` sits between condition red and amber, so on the map it
could be mistaken for a hazard. Decided: no accent on the map (Decision 5).
