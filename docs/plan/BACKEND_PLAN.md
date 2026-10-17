# Backend plan (Dimi)

Branches in merge order. Each is one Claude Code prompt and one small PR.
Endpoint IDs (E1–E9) refer to [API_CONTRACT.md](API_CONTRACT.md#endpoints).
After each merge, send the message from [WORKFLOW.md](WORKFLOW.md#communication).

## Design rule

**AI interprets photos; deterministic Python computes everything else.**

| Gemini decides | Python decides (pure functions, unit-tested) |
|---|---|
| `hazard_type`, `description`, `ai_confidence` | `condition`, `freshness_weight`, `verification_status`, `needs_review`, segment and route `score`, `explanation` strings |

- Gemini output is forced into a JSON schema (enum for `hazard_type`) and validated; anything
  invalid = AI failure. Text in a photo can't change scores because scores never come from the model.
- Tests and CI never call Gemini (`config/settings_test.py` forces mock).

## Overview

| # | Branch | Makes live | Milestone |
|---|---|---|---|
| 1 | `feat/report-models` | — | — |
| 2 | `feat/reports-api` | E2, E3, E4 | **M1** |
| 3 | `feat/gemini-analysis` | — (internal) | — |
| 4 | `feat/report-upload` | E5 | **M2** |
| 5 | `feat/freshness-verification` | E6 (+ real `condition`/`freshness_weight` in E3–E5) | **M3** |
| 6 | `feat/route-scoring` | E7, E8, E9 | **M4** |
| 7 | `feat/demo-data` | seed data for all endpoints | **M5** |
| 8 | `chore/ci-make-check` | — | — |

---

### 1. `feat/report-models`

- **Goal:** `Report` and `ReportFeedback` models in `reports`, admin registration, migrations.
- **Details:** fields exactly as [Report object](API_CONTRACT.md#report-object); enums as
  `TextChoices` in one module (single source for E2). `photo` = `ImageField` → adds **Pillow**
  (image library Django needs to validate image files). `ReportFeedback` stores report, action,
  session key, timestamp (for `duplicate_feedback`). No PostGIS/GeoDjango: plain float lat/lng.
  Synthetic fixture `reports/fixtures/demo_reports.json` (`make loaddemo`, no photos).
- **Live:** none.
- **Done when:** `make check` green; admin can create/edit a report; model tests for defaults.
- **Frontend can switch from mock to live for:** none.

### 2. `feat/reports-api`

- **Goal:** read-only API + the contract error format.
- **Live:** [E2 meta](API_CONTRACT.md#e2-meta), [E3 list](API_CONTRACT.md#e3-list-reports),
  [E4 detail](API_CONTRACT.md#e4-report-detail).
- **Details:** DRF custom exception handler producing `{"error": {code, message, fields}}` for
  all errors (incl. 404/405/CSRF). `bbox` parsing + validation. No new fixture: there is
  **one** fixture, `reports/fixtures/demo_reports.json` from branch 1, reused by later branches
  so the map has data before branch 7. `condition` = simple placeholder in
  `reports/condition.py` until branch 5.
- **Done when:** tests compare each response's **keys and types** against the contract
  examples; bad bbox → 400 `invalid_bbox`; unknown id → 404 `not_found` in contract format.
- **Frontend can switch from mock to live for:** E2, E3, E4.

### 3. `feat/gemini-analysis`

- **Goal:** `ai` app service: `analyze_image(bytes, mime) -> AnalysisResult | raises AiRateLimited / AiUnavailable`.
- **Details:** adds **google-genai** (Google's official Gemini SDK). Model from
  `settings.GEMINI_MODEL`, key from `settings.GEMINI_API_KEY`, never logged. Structured JSON
  output with `hazard_type` enum. Timeout ~15 s. `AI_MODE=mock` → deterministic fake result
  (chosen from a hash of the photo bytes), no network. Free-tier 429 → `AIRateLimited`.
- **Live:** none (internal).
- **Done when:** unit tests for mock mode, response validation (bad JSON → `AiUnavailable`, unknown enum → `other` + needs_review),
  and a test proving no live client is created under test settings. One manual live run documented in the PR.
- **Frontend can switch from mock to live for:** none.

### 4. `feat/report-upload`

- **Goal:** create reports from photos.
- **Live:** [E5 create](API_CONTRACT.md#e5-create-report).
- **Details:** validate type (by content via Pillow, not just extension), size ≤ 10 MB, bounds,
  note length. Re-save image without EXIF (`ai.image.prepare_image` can be reused). Call
  `analyze_image`; on `AiUnavailable` → create with `needs_review=true`, `ai_flagged`, `grey`;
  on `AiRateLimited` → 429, nothing saved. Store `result.raw_response` (or
  `exc.raw_response`) in `Report.ai_raw_response`.
  CSRF enforced for this endpoint even though users are anonymous.
- **Done when:** tests for 201 (mock AI), AI failure → 201 flagged, rate limit → 429 no row,
  413, 415, 400 cases, missing CSRF → 403 `csrf_failed`.
- **Frontend can switch from mock to live for:** E5.

### 5. `feat/freshness-verification`

- **Goal:** feedback endpoint + deterministic freshness/condition/status.
- **Live:** [E6 feedback](API_CONTRACT.md#e6-report-feedback); E3–E5 now return real
  `condition` and `freshness_weight`.
- **Details (starting values, tune freely without a contract change):**
  - `freshness_weight = 0.5 ** (hours_since_last_confirmed / half_life_hours)`
  - half-life: cars 2 h, `road_block` 48 h, `construction_debris` 7 d, `pothole_damage` 30 d,
    `informal_shortcut` 90 d, `other` 24 h.
  - condition: `grey` if needs_review/disputed or weight < 0.2; `green` if resolved, `none` or
    `informal_shortcut`; `red` if weight ≥ 0.5; else `amber`.
  - status thresholds: 2× `still_there` → `community_confirmed`; 2× `resolved` → `resolved`;
    2× `dispute` → `disputed`. Duplicate per session → 409.
  - Computed on read (no cron job needed).
- **Done when:** table-driven unit tests for the pure functions (frozen time); endpoint tests incl. 409.
- **Frontend can switch from mock to live for:** E6.

### 6. `feat/route-scoring`

- **Goal:** segments, demo scenarios, route comparison.
- **Live:** [E7](API_CONTRACT.md#e7-segments), [E8](API_CONTRACT.md#e8-route-scenarios),
  [E9](API_CONTRACT.md#e9-route-comparison).
- **Details:** hand-drawn geometry in `routes/data/*.geojson` (no routing engine). A report is
  "on" a route/segment if within 25 m (equirectangular distance, no GIS libraries).
  `score = clamp(100 − Σ penalty(hazard_type) × freshness_weight × status_factor − kind_penalty, 0, 100)`;
  score → condition: ≥ 75 green, ≥ 50 amber, else red. `explanation` strings built from the same numbers.
- **Done when:** unit tests: adding a fresh red report on a route lowers its score and can change
  `recommended_route_id`; GeoJSON coordinates verified `[lng, lat]`.
- **Frontend can switch from mock to live for:** E7, E8, E9.

### 7. `feat/demo-data`

- **Goal:** repeatable demo.
- **Details:** `python manage.py seed_demo [--reset]` (+ `make seed`): idempotent, creates
  labelled synthetic reports (`is_synthetic=true`) with photos from `demo/photos/` (each
  < 500 KB — pre-commit blocks larger files; only photos we took or CC0) and **cached AI results**
  stored as JSON so the demo never depends on the Gemini quota.
- **Done when:** `make migrate && make seed && make run` shows a full demo on a fresh clone.
- **Frontend can switch from mock to live for:** none new → **M5: run the demo together.**

### 8. `chore/ci-make-check`

- **Goal:** CI and local run the same thing.
- **Details:** CI test job runs `make check` (keeps separate jobs; gitleaks job unchanged).
  Pin `bandit`, `pip-audit`, `pytest` in `requirements-dev.txt`. Must not remove or weaken any check.
- **Done when:** CI green on the PR; diff shows only additions/pins.
- **Frontend can switch from mock to live for:** none.
