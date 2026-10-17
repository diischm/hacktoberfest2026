# Team workflow

Two developers, two Claude Code sessions, one repo, 8 hours.

| Who | Role | Plan |
|---|---|---|
| Dimi | Backend: models, API, Gemini, scoring, settings | [BACKEND_PLAN.md](BACKEND_PLAN.md) |
| Frontend dev | Frontend/design: map, upload, route comparison UI, PWA, styling | [Frontend plan](#frontend-plan) |

Shared contract: [API_CONTRACT.md](API_CONTRACT.md). Backend → frontend facts: [FRONTEND_NOTES.md](FRONTEND_NOTES.md).

## Branches

| Prefix | For |
|---|---|
| `feat/` | New functionality |
| `fix/` | Bug fix |
| `docs/` | Docs only (incl. contract changes) |
| `chore/` | Tooling, CI, dependencies |

- One branch per Claude Code prompt. Small PRs (aim < 400 changed lines).
- Lowercase, hyphens: `feat/upload-screen`.

## Every branch, every time

```bash
# start
git checkout main && git pull
git checkout -b feat/<name>

# before opening the PR
git fetch && git rebase origin/main
make check          # must be green
git push -u origin feat/<name>     # force-push your OWN branch after rebase is fine: --force-with-lease
```

## Merge rule

1. CI green **and** a quick look (approve) from the other person.
2. Whoever is green first merges (squash merge). The other one rebases onto `origin/main`.
3. Never force-push `main`. Never push directly to `main`.

## Who waits for whom

- **Frontend never waits:** works on mocks (`web/static/web/mock/*.json`) until a milestone is announced.
- **Backend never waits on frontend.**
- The only sync points are **contract changes** and this table:

| Milestone | Backend branch merged | Frontend action |
|---|---|---|
| M1 reports readable (E2, E3, E4) | `feat/reports-api` | Switch map to live |
| M2 upload live (E5) | `feat/report-upload` | Switch upload form to live |
| M3 feedback live (E6) | `feat/freshness-verification` | Switch confirm/dispute buttons to live |
| M4 routes live (E7, E8, E9) | `feat/route-scoring` | Switch route comparison to live |
| M5 demo data | `feat/demo-data` | Final demo run-through together |

## Contract change process

1. Whoever needs a change opens a small `docs/contract-<what>` PR editing **only**
   `docs/plan/API_CONTRACT.md`: bump `contract_version`, add a changelog row.
2. The other person approves it.
3. Only then is code changed (backend and/or frontend mocks).

Backend must not rename, remove or change the type of a contract field without this.
Adding a new optional field is still a contract change (bump), but the other side may merge it fast.

## Communication

After every merge, one line in the team chat:

```
merged <branch> — contract vX — frontend can now switch: <endpoint IDs or none>
```

Example: `merged feat/reports-api — contract v1 — frontend can now switch: E2, E3, E4`

## Conflict hot-spots

| File | Owner | Rule |
|---|---|---|
| `config/settings.py` | Backend | Frontend's first PR only: add `"web"` to `INSTALLED_APPS` (see [FRONTEND_NOTES.md](FRONTEND_NOTES.md#one-time-shared-edit-frontends-first-pr)) |
| `config/urls.py` | Backend | Frontend's first PR only: `path("", include("web.urls"))` replaces the placeholder `/` route |
| `config/views.py`, top-level `templates/` | Backend | Backend deletes the placeholder home page after the frontend's first PR ([Handoffs](#handoffs)) |
| `tests/` | Backend | Frontend never edits or deletes these ([Handoffs](#handoffs)) |
| `requirements*.txt`, `pyproject.toml` | Backend | Frontend asks if it needs a package or config |
| `Makefile`, `.github/`, `.pre-commit-config.yaml` | Backend | — |
| `docs/plan/API_CONTRACT.md` | Both | Only via the contract change process |
| `web/` (incl. `web/templates/web/`, `web/static/web/`, `web/tests/`) | Frontend | Backend doesn't touch it |
| `docs/design/` (mockups, screenshots, design README) | Frontend | Backend doesn't touch it |
| `README.md` | Both | Keep edits small, rebase before merge |

## Handoffs

**Rule: if a PR would need to change a test owned by the other person, stop and ask them first.**

### Home page (`/`)

| Step | Who | What |
|---|---|---|
| Now | — | `tests/test_home.py` (backend) checks `GET /` → 200, body contains `BikeAble` and a `<meta name="viewport" ...>` tag |
| 1 | Frontend, first PR | `/` now comes from `web.urls`. That page **must contain the text `BikeAble` and a viewport meta tag** so `tests/test_home.py` keeps passing. Frontend must not edit or delete anything in `tests/` |
| 2 | Backend, next branch after step 1 merges | Delete the `home` view from `config/views.py` and `templates/home.html`; add `"web"` to `testpaths` in `pyproject.toml` (today it is `["tests"]`, so `web/tests/` would not be collected by `make check`/CI) |
| 3 | Frontend, if needed | Add its own tests under `web/tests/` |

## End of day

- **Freeze `main` 1 hour before the demo.** After that only `fix/` branches, each approved by both.
- Final run-through on a fresh clone: `make install && make migrate && make seed && make run`.

## Frontend plan

Branches in merge order. Each is one Claude Code prompt and one small PR, all inside `web/`
(except the one-time edit in branch 1). Follows [API_CONTRACT.md](API_CONTRACT.md),
[FRONTEND_NOTES.md](FRONTEND_NOTES.md) and [docs/design/README.md](../design/README.md).

Frontend never waits: every screen is built on mocks first. A branch flips its
`API_MODE` keys to `"live"` only after the matching milestone message from backend
(`merged <branch> — contract vX — frontend can now switch: ...`).

**Every screen covers three states:** empty (no data), loading, and error (branch on
`error.code`, show `error.message`).

| # | Branch | Builds | Goes live after |
|---|---|---|---|
| 1 | `feat/web-skeleton` | `web/` app, base template, CSS tokens | — (merge first) |
| 2 | `feat/mock-api-layer` | mock JSON, `config.js`, `api.js` | — |
| 3 | `feat/map-reports` | map, markers, report detail | **M1** → `meta`, `reports`, `reportDetail` |
| 4 | `feat/upload-screen` | photo upload | **M2** → `createReport` |
| 5 | `feat/report-feedback` | confirm / gone / dispute buttons | **M3** → `feedback` |
| 6 | `feat/route-compare` | scenarios, segments, route cards | **M4** → `segments`, `scenarios`, `compare` |
| 7 | `feat/pwa-polish` | manifest, service worker, styling pass, `web/tests/` | **M5** → demo run-through together |

Branch 2 may start before 1 merges (rebase after). Branches 3–7 rebase on whatever is merged.

### 1. `feat/web-skeleton`

- **First frontend code PR, merge as early as possible** (before backend's settings edits pile up).
- Creates the `web` app: `apps.py`, `urls.py`, `views.py`, `templates/web/base.html`,
  `templates/web/index.html`, `static/web/css/tokens.css` (design tokens from
  [docs/design/README.md](../design/README.md)).
- **The only PR that touches files outside `web/`:** `config/settings.py` (add `"web",` to
  `INSTALLED_APPS`) and `config/urls.py` (`path("", include("web.urls"))`). Announce in chat.
- `/` page **must contain `BikeAble` and a `<meta name="viewport" ...>` tag** so backend's
  `tests/test_home.py` stays green. Don't edit `tests/`.
- After merge, backend deletes the placeholder home view and adds `web` to `testpaths`.

### 2. `feat/mock-api-layer`

- `web/static/web/mock/*.json`: exact copies of the contract examples (file names from the
  [endpoint table](API_CONTRACT.md#endpoints)), plus `error-ai-rate-limited.json`.
- `config.js` with the per-endpoint `API_MODE` switch; `api.js` wraps `fetch`: relative
  `/api/...` URLs with trailing `/`, `X-CSRFToken` on POST, parses the `{"error": {...}}`
  format, fake 2–5 s delay on mock POSTs.

### 3. `feat/map-reports`

- Leaflet + OSM tiles (attribution required). Center/zoom/bounds, labels and condition
  colors from `GET /api/meta/`, never hardcoded.
- Markers from E3 via `L.geoJSON()` (GeoJSON is `[lng, lat]`); reload on `moveend` with
  `bbox = map.getBounds().toBBoxString()`. `freshness_weight` → marker opacity.
- Report detail sheet from E4: photo (`photo_url` may be `null`), description, note,
  status, counts, "needs review" mark, **"Demo data" badge when `is_synthetic`**.
- Unknown `hazard_type` → `other`; unknown `condition` → `grey`.
  `informal_shortcut` is shown as information, not a hazard.

### 4. `feat/upload-screen`

- `<input type="file" accept="image/*" capture="environment">`; location by tapping the map
  (GPS only as a bonus: blocked on `http://<LAN-IP>`). Note ≤ `meta.upload.max_note_length`.
- **Resize in the browser before POST:** canvas → JPEG, ~1600 px long edge (smaller, faster,
  drops EXIF/GPS). Check type/size against `meta.upload` first.
- Loading state, submit disabled, client timeout ≥ 30 s. Errors: 400 (inline `fields`),
  413, 415, 429 (`retry_after_seconds` → "try again in N s"). AI failure is a 201 with
  `needs_review: true`: show it as "saved, needs review".

### 5. `feat/report-feedback`

- Buttons from `meta.feedback_actions` on the detail sheet → E6; re-render the returned
  report object (don't compute status/condition locally). 409 `duplicate_feedback` →
  friendly "you already said that".

### 6. `feat/route-compare`

- Scenario picker (E8), segments layer colored by `condition` (E7), route comparison (E9):
  routes drawn with `L.geoJSON()`, cards ordered as returned with score, condition, length
  and the `explanation` list; `recommended_route_id` highlighted; tap a card to focus its line.

### 7. `feat/pwa-polish`

- `manifest.json`, icons, `/sw.js` served by a `web` view (scope `/`, not `/static/`).
- **Service worker and "install app" only work on https or `localhost`.** On
  `http://<LAN-IP>:8000` the app works but won't install or cache offline. Decide here
  whether that's acceptable for the demo or needs an https tunnel.
- Final styling pass at phone width (~390 px), accessibility basics (contrast, tap targets,
  labels), `web/tests/` for views (`/` 200, `/sw.js` content type).
