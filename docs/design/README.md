# BikeAble design

Frontend-owned. How the UI should look, and how to turn the design into the real app.

> **Status: mockup pending.** No mockup source (`mockup.html` / `mockup.jsx`) or phone
> screenshots are in this folder yet. Sections marked *pending* get filled from the mockup
> once it is added. Until then, follow [Style direction](#style-direction).

## Screen inventory

*Pending mockup.* Planned screens and the branch that builds each:

| Screenshot | Screen | Branch |
|---|---|---|
| `screens/01-map.png` | Map with report markers + legend | `feat/map-reports` |
| `screens/02-report-detail.png` | Report detail sheet + feedback buttons | `feat/map-reports`, `feat/report-feedback` |
| `screens/03-upload.png` | Photo upload | `feat/upload-screen` |
| `screens/04-route-compare.png` | Route comparison | `feat/route-compare` |

Only name screens the mockup actually has; drop rows that don't exist.

## Style direction

Taken from mood references (kept locally, **not committed**: third-party work, not ours to
redistribute). Describe them here; don't copy their assets.

- **Scrapbook / analog collage:** paper cards on a flat colored ground, slightly rotated
  "taped" or "pinned" cards, photos with white borders like prints.
- **Ground:** muted deep green with subtle grain or grid; paper cards in off-white / cream.
- **Type:** a typewriter / monospace face for labels and data (receipt-style rows with
  dotted leaders), a clean sans for body, optional handwritten accent for headings only.
- **Details:** hand-drawn doodles, stickers, receipt edges. Use sparingly; the map is the hero.

Constraints that win over the mood:

- Condition colors are functional, not decorative: markers, segments and routes use the
  `/api/meta/` hex values. Amber `#F9A825` has low contrast on cream: pair it with a dark
  outline or icon, never amber text on paper.
- Rotation/tape effects go on cards and sheets, never on the map, buttons or form inputs.
- Tap targets ≥ 44 px, body text ≥ 16 px at phone width.

## Design tokens

*Pending mockup.* Extract exact values from the mockup source into
`web/static/web/css/tokens.css` as CSS custom properties:

| Group | Tokens |
|---|---|
| Colors | `--color-ground`, `--color-paper`, `--color-ink`, `--color-ink-muted`, `--color-accent` (conditions come from `/api/meta/` at runtime) |
| Fonts | `--font-body`, `--font-mono`, `--font-hand` |
| Font sizes | `--fs-sm`, `--fs-md`, `--fs-lg`, `--fs-xl` |
| Spacing | `--space-1` … `--space-6` |
| Radius | `--radius-sm`, `--radius-md` |
| Shadows | `--shadow-card`, `--shadow-sheet` |
| Breakpoints | phone first; one breakpoint for tablet/desktop |

## Components

*Pending mockup.* Expected: bottom sheet, primary/secondary button, condition badge,
"Demo data" badge, "Needs review" badge, map legend, report card, route card, upload form,
toast for errors.

## Translation rules

- The mockup is a **reference for layout and style only.** The real app is Django templates
  + vanilla JS + Leaflet, **no build step**.
- Do not copy React, JSX, npm packages or build tooling.
- CSS framework or icon library in the mockup: use it only if it loads from a CDN with a
  plain `<script>`/`<link>` and no build; otherwise replace it with plain CSS / inline SVG.
  Google Fonts via `<link>` is fine.
- **All data in the mockup is fake.** Real labels, hazard types and condition colors come
  from `GET /api/meta/`. Real report and route fields are only those in
  [API_CONTRACT.md](../plan/API_CONTRACT.md).

## Mismatches (needs decision)

*Pending mockup.* Check: condition colors vs `/api/meta/`, fields not in the Report object or
E9 response, screens/actions with no endpoint. Any mismatch → a `docs/contract-*` PR for
backend to approve; don't change the contract here.
