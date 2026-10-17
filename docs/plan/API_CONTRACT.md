# BikeAble API contract

**contract_version: 2**

Single source of truth between frontend and backend. If code and this file disagree, this
file wins and the code is a bug. Change it only via the process in
[WORKFLOW.md](WORKFLOW.md#contract-change-process).

## Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/` — every path ends with `/` (Django redirects or 404s without it; POST without it fails) |
| Format | JSON (`Content-Type: application/json`), except `POST /api/reports/` which takes `multipart/form-data` |
| Auth | None (anonymous). POST requests must send the CSRF header, see [FRONTEND_NOTES.md](FRONTEND_NOTES.md#csrf) |
| Timestamps | ISO 8601 **with timezone offset**, server time zone `Europe/Skopje`, e.g. `"2026-10-17T10:15:00+02:00"` |
| Coordinates | WGS84 decimal degrees |
| Plain objects | Always named keys: `{"lat": 41.9962, "lng": 21.4316}` — never a bare array |
| **GeoJSON** | **`coordinates` are `[lng, lat]` (longitude first!)**. Leaflet `L.latLng`/`L.marker`/`L.polyline` take `[lat, lng]`. `L.geoJSON()` swaps automatically; anything manual must swap. This is the #1 map bug. |
| `bbox` param | `minLng,minLat,maxLng,maxLat` (longitude first, same as GeoJSON). Leaflet `map.getBounds().toBBoxString()` produces exactly this. |
| IDs | Reports and segments: integer. Routes and scenarios: string slug |
| Unknown enum values | Frontend must not crash: unknown `hazard_type` → render as `other`; unknown `condition` → render as `grey` |
| Labels and colors | Frontend reads them from [`GET /api/meta/`](#e2-meta), never hardcodes them |

## Error format

Every non-2xx response has this body:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary, safe to show to the user.",
    "fields": {
      "lat": ["Must be a number between -90 and 90."]
    }
  }
}
```

- `code`: string from the table below. The frontend branches on `code`, never on `message`.
- `message`: string (English).
- `fields`: object mapping field name → list of messages. **Always present**; `{}` when no field is at fault.
- Some codes add extra keys inside `error` (listed in the table).

| HTTP | `code` | When | Extra keys |
|---|---|---|---|
| 400 | `validation_error` | Bad/missing body or query param | — |
| 400 | `invalid_bbox` | `bbox` not 4 numbers, out of range, or min > max | — |
| 403 | `csrf_failed` | Missing/invalid CSRF token on POST | — |
| 404 | `not_found` | Unknown id / scenario / path | — |
| 405 | `method_not_allowed` | Wrong HTTP method | — |
| 409 | `duplicate_feedback` | Same browser session already sent this action for this report | — |
| 413 | `photo_too_large` | Photo > 10 MB | — |
| 415 | `unsupported_photo_type` | Photo not JPEG/PNG/WebP | — |
| 429 | `ai_rate_limited` | Gemini free-tier quota hit; report **not** created, retry later | `retry_after_seconds` (int). Also `Retry-After` header |
| 500 | `server_error` | Bug | — |

## Report object

Used by E4, E5, E6 (flat object) and as GeoJSON `properties` in E3 (same fields **minus `lat`/`lng`**, which are in `geometry`).

| Field | Type | Values / notes |
|---|---|---|
| `id` | int | |
| `lat` | number | WGS84, ≤ 6 decimals |
| `lng` | number | WGS84, ≤ 6 decimals |
| `hazard_type` | string enum | see [Hazard types](#hazard-types) |
| `description` | string | Short AI-written description of the photo; `""` if AI failed |
| `note` | string | User's optional note from upload; `""` if none (max 500 chars) |
| `ai_confidence` | number \| null | 0–1; `null` if AI failed or not run |
| `needs_review` | bool | `true` if AI failed or confidence is low. UI should mark it as "needs review" |
| `verification_status` | string enum | see [Verification statuses](#verification-statuses) |
| `condition` | string enum | `green` \| `amber` \| `red` \| `grey`. **Computed by backend. Frontend only renders it** (color from E2) |
| `freshness_weight` | number | 0–1. 1 = just reported/confirmed, decays over time. Frontend may use it for opacity |
| `created_at` | string | ISO 8601 |
| `last_confirmed_at` | string | ISO 8601. Equals `created_at` until someone sends `still_there` |
| `photo_url` | string \| null | Use as-is in `<img src>`. `null` if no photo (some seed data) |
| `is_synthetic` | bool | `true` = demo data, **UI must visibly label it** (e.g. "Demo data" badge) |
| `feedback_counts` | object | `{"still_there": int, "resolved": int, "dispute": int}` |

### Hazard types

| key | meaning | is_hazard |
|---|---|---|
| `road_block` | Road/bike lane physically blocked | true |
| `car_on_sidewalk` | Car parked on sidewalk | true |
| `car_on_crosswalk` | Car parked on a zebra crossing | true |
| `car_in_bike_lane` | Car parked/stopped in a bike lane | true |
| `pothole_damage` | Pothole or damaged surface | true |
| `construction_debris` | Construction material/debris in the way | true |
| `informal_shortcut` | Worn human-made path (e.g. through bushes/grass). **Information, not necessarily a hazard** | false |
| `other` | Something else the AI couldn't classify | true |
| `none` | AI found no hazard in the photo | false |

### Verification statuses

| key | meaning (backend decides transitions) |
|---|---|
| `unverified` | New report, AI result looks fine, no community input yet |
| `ai_flagged` | AI failed or low confidence (`needs_review: true`) |
| `community_confirmed` | Enough users said `still_there` |
| `verified` | Confirmed by an admin |
| `disputed` | Enough users said `dispute` |
| `resolved` | Enough users said `resolved`, or admin. Hidden from E3 unless `include_resolved=true` |

### Conditions

| key | hex | meaning |
|---|---|---|
| `green` | `#2E7D32` | Clear / comfortable |
| `amber` | `#F9A825` | Minor issue or aging report |
| `red` | `#C62828` | Fresh, significant hazard |
| `grey` | `#757575` | Unknown, stale, disputed or needs review |

(Values here are what E2 returns. If they differ, E2 wins and this table gets fixed.)

## Endpoints

| ID | Method | Path | Mock file (frontend) |
|---|---|---|---|
| E1 | GET | `/api/health/` | — |
| E2 | GET | `/api/meta/` | `web/static/web/mock/meta.json` |
| E3 | GET | `/api/reports/` | `web/static/web/mock/reports.json` |
| E4 | GET | `/api/reports/{id}/` | `web/static/web/mock/report-101.json` |
| E5 | POST | `/api/reports/` | `web/static/web/mock/report-create.json` |
| E6 | POST | `/api/reports/{id}/feedback/` | `web/static/web/mock/report-feedback.json` |
| E7 | GET | `/api/segments/` | `web/static/web/mock/segments.json` |
| E8 | GET | `/api/routes/scenarios/` | `web/static/web/mock/scenarios.json` |
| E9 | GET | `/api/routes/compare/` | `web/static/web/mock/routes-compare.json` |
| E10 | GET | `/api/bike-parking/` | `web/static/web/mock/bike-parking.json` |

### E1 Health

`GET /api/health/` — **exists already.** No params.

```json
{"status": "ok", "ai_mode": "mock"}
```

`ai_mode`: `"mock"` | `"live"`. Never exposes the API key. Errors: none expected.

### E2 Meta

`GET /api/meta/` — no params. Labels, colors and limits. Frontend loads it once at startup.

```json
{
  "contract_version": 2,
  "hazard_types": [
    {"key": "road_block", "label": "Road blocked", "icon": "barrier", "is_hazard": true},
    {"key": "car_on_sidewalk", "label": "Car on sidewalk", "icon": "car", "is_hazard": true},
    {"key": "car_on_crosswalk", "label": "Car on crosswalk", "icon": "car", "is_hazard": true},
    {"key": "car_in_bike_lane", "label": "Car in bike lane", "icon": "car", "is_hazard": true},
    {"key": "pothole_damage", "label": "Pothole / damage", "icon": "pothole", "is_hazard": true},
    {"key": "construction_debris", "label": "Construction debris", "icon": "cone", "is_hazard": true},
    {"key": "informal_shortcut", "label": "Informal shortcut path", "icon": "footpath", "is_hazard": false},
    {"key": "other", "label": "Other", "icon": "warning", "is_hazard": true},
    {"key": "none", "label": "No hazard found", "icon": "check", "is_hazard": false}
  ],
  "conditions": [
    {"key": "green", "hex": "#2E7D32", "label": "Clear", "meaning": "Clear / comfortable"},
    {"key": "amber", "hex": "#F9A825", "label": "Caution", "meaning": "Minor issue or aging report"},
    {"key": "red", "hex": "#C62828", "label": "Hazard", "meaning": "Fresh, significant hazard"},
    {"key": "grey", "hex": "#757575", "label": "Unknown", "meaning": "Unknown, stale, disputed or needs review"}
  ],
  "verification_statuses": [
    {"key": "unverified", "label": "Unverified"},
    {"key": "ai_flagged", "label": "Needs review"},
    {"key": "community_confirmed", "label": "Confirmed by riders"},
    {"key": "verified", "label": "Verified"},
    {"key": "disputed", "label": "Disputed"},
    {"key": "resolved", "label": "Resolved"}
  ],
  "feedback_actions": [
    {"key": "still_there", "label": "Still there"},
    {"key": "resolved", "label": "It's gone"},
    {"key": "dispute", "label": "Not accurate"}
  ],
  "segment_kinds": [
    {"key": "bike_lane", "label": "Bike lane or cycleway", "hex": "#1565C0", "line_style": "solid"},
    {"key": "shared_path", "label": "Shared path", "hex": "#00838F", "line_style": "dashed"},
    {"key": "road", "label": "On-street (no lane)", "hex": "#6D4C41", "line_style": "dotted"},
    {"key": "informal_path", "label": "Informal path", "hex": "#8D6E63", "line_style": "dashed"}
  ],
  "bike_parking": {"label": "Bicycle parking", "hex": "#0D47A1"},
  "upload": {
    "max_photo_bytes": 10485760,
    "accepted_types": ["image/jpeg", "image/png", "image/webp"],
    "max_note_length": 500
  },
  "map": {
    "center": {"lat": 41.9962, "lng": 21.4316},
    "zoom": 15,
    "bounds": {"min_lat": 41.95, "min_lng": 21.30, "max_lat": 42.05, "max_lng": 21.55}
  }
}
```

- `icon` is a **hint** (a name, not a file); frontend maps it to its own icon set and falls back to a generic marker.
- `map.center`/`zoom` are placeholders (Macedonia Square) until the demo area is confirmed.
- `map.bounds`: uploads outside it are rejected (E5).
- `segment_kinds`: line `hex` and `line_style` (`solid` | `dashed` | `dotted`) per `kind` for E7
  segments. The frontend must read them here, never hardcode them.
- `bike_parking`: `label` and `hex` for the E10 parking spots.

Errors: none expected.

### E3 List reports

`GET /api/reports/?bbox=minLng,minLat,maxLng,maxLat&include_resolved=false`

| Param | Required | Type | Default | Notes |
|---|---|---|---|---|
| `bbox` | no | 4 comma-separated numbers | whole `map.bounds` | lng first |
| `include_resolved` | no | `true` \| `false` | `false` | `false` hides `verification_status: resolved` |

Returns a GeoJSON `FeatureCollection` of `Point`s, newest first, max 500 features.
`properties` = [Report object](#report-object) without `lat`/`lng`.
`truncated: true` (non-standard top-level member) when more than 500 matched.

```json
{
  "type": "FeatureCollection",
  "truncated": false,
  "features": [
    {
      "type": "Feature",
      "id": 101,
      "geometry": {"type": "Point", "coordinates": [21.4316, 41.9962]},
      "properties": {
        "id": 101,
        "hazard_type": "car_in_bike_lane",
        "description": "A silver car is parked across the painted bike lane.",
        "note": "Every morning around 8",
        "ai_confidence": 0.91,
        "needs_review": false,
        "verification_status": "community_confirmed",
        "condition": "red",
        "freshness_weight": 0.86,
        "created_at": "2026-10-17T08:05:00+02:00",
        "last_confirmed_at": "2026-10-17T09:40:00+02:00",
        "photo_url": "/media/reports/2026/10/101.jpg",
        "is_synthetic": false,
        "feedback_counts": {"still_there": 2, "resolved": 0, "dispute": 0}
      }
    },
    {
      "type": "Feature",
      "id": 102,
      "geometry": {"type": "Point", "coordinates": [21.4251, 41.9978]},
      "properties": {
        "id": 102,
        "hazard_type": "informal_shortcut",
        "description": "A worn dirt path cuts diagonally through the grass.",
        "note": "",
        "ai_confidence": 0.78,
        "needs_review": false,
        "verification_status": "unverified",
        "condition": "green",
        "freshness_weight": 0.99,
        "created_at": "2026-10-16T17:30:00+02:00",
        "last_confirmed_at": "2026-10-16T17:30:00+02:00",
        "photo_url": null,
        "is_synthetic": true,
        "feedback_counts": {"still_there": 0, "resolved": 0, "dispute": 0}
      }
    }
  ]
}
```

Errors: 400 `invalid_bbox`, 400 `validation_error` (bad `include_resolved`).

### E4 Report detail

`GET /api/reports/{id}/` — full flat [Report object](#report-object) (includes `lat`, `lng`).

```json
{
  "id": 101,
  "lat": 41.9962,
  "lng": 21.4316,
  "hazard_type": "car_in_bike_lane",
  "description": "A silver car is parked across the painted bike lane.",
  "note": "Every morning around 8",
  "ai_confidence": 0.91,
  "needs_review": false,
  "verification_status": "community_confirmed",
  "condition": "red",
  "freshness_weight": 0.86,
  "created_at": "2026-10-17T08:05:00+02:00",
  "last_confirmed_at": "2026-10-17T09:40:00+02:00",
  "photo_url": "/media/reports/2026/10/101.jpg",
  "is_synthetic": false,
  "feedback_counts": {"still_there": 2, "resolved": 0, "dispute": 0}
}
```

Errors: 404 `not_found`. Resolved reports are still returned here.

### E5 Create report

`POST /api/reports/` — `multipart/form-data`, header `X-CSRFToken`.

| Field | Required | Type | Rules |
|---|---|---|---|
| `photo` | yes | file | JPEG, PNG or WebP; ≤ 10 MB (10 485 760 bytes) |
| `lat` | yes | number (as text) | −90..90 and inside `meta.map.bounds` |
| `lng` | yes | number (as text) | −180..180 and inside `meta.map.bounds` |
| `note` | no | string | ≤ 500 chars |

- **Synchronous**: the AI runs inside the request. Can take **up to ~15 s**. Frontend must show a
  loading state, disable the submit button, and use a client timeout of **≥ 30 s**.
- **AI failure** (timeout, bad answer, any error except rate limit): report **is still created** →
  `201` with `hazard_type: "other"`, `description: ""`, `ai_confidence: null`,
  `needs_review: true`, `verification_status: "ai_flagged"`, `condition: "grey"`.
- **Rate limit** (Gemini free tier): `429 ai_rate_limited`, report **not** created, user can retry.
- Backend strips EXIF metadata (incl. GPS) from stored photos.

Response `201` — the created [Report object](#report-object) (flat, same shape as E4):

```json
{
  "id": 103,
  "lat": 41.9951,
  "lng": 21.4302,
  "hazard_type": "car_on_crosswalk",
  "description": "A black SUV is stopped on the zebra crossing.",
  "note": "",
  "ai_confidence": 0.87,
  "needs_review": false,
  "verification_status": "unverified",
  "condition": "red",
  "freshness_weight": 1.0,
  "created_at": "2026-10-17T11:02:13+02:00",
  "last_confirmed_at": "2026-10-17T11:02:13+02:00",
  "photo_url": "/media/reports/2026/10/103.jpg",
  "is_synthetic": false,
  "feedback_counts": {"still_there": 0, "resolved": 0, "dispute": 0}
}
```

Rate-limit example (`429`):

```json
{
  "error": {
    "code": "ai_rate_limited",
    "message": "The photo analyzer is busy. Please try again in a minute.",
    "fields": {},
    "retry_after_seconds": 60
  }
}
```

Errors: 400 `validation_error` (missing photo/lat/lng, out of bounds, note too long),
403 `csrf_failed`, 413 `photo_too_large`, 415 `unsupported_photo_type`, 429 `ai_rate_limited`.

### E6 Report feedback

`POST /api/reports/{id}/feedback/` — JSON body, header `X-CSRFToken`.

```json
{"action": "still_there"}
```

`action`: `still_there` | `resolved` | `dispute`.

Response `200` — the updated [Report object](#report-object) (flat). Example after the request above
on report 101: `feedback_counts.still_there` 2 → 3, `last_confirmed_at` = now, `freshness_weight` 1.0.
Status/condition changes are decided by the backend; the frontend just re-renders the returned object.

Errors: 400 `validation_error` (unknown action), 403 `csrf_failed`, 404 `not_found`,
409 `duplicate_feedback` (same session, same report, same action).

### E7 Segments

`GET /api/segments/?bbox=minLng,minLat,maxLng,maxLat` — `bbox` optional, same rules as E3.

GeoJSON `FeatureCollection` of `LineString`s (bike-lane/road segments in the demo area).

These are the **real, existing** lanes and paths from OpenStreetMap (downloaded with
`manage.py fetch_bike_data`, committed as `reports/data/skopje_bike.geojson`), so
`is_synthetic` is `false`. `condition`/`score` are computed live from the current reports, exactly
like report conditions. `osm_timestamp` (non-standard top-level member) is the OSM snapshot time.

| property | type | notes |
|---|---|---|
| `id` | int | OpenStreetMap way id |
| `name` | string | e.g. street name, may be `""` |
| `kind` | enum | `bike_lane` \| `road` \| `shared_path` \| `informal_path` (colors in E2 `segment_kinds`) |
| `condition` | enum | `green` \| `amber` \| `red` \| `grey`, computed by backend |
| `score` | int | 0–100, higher = more comfortable |
| `length_m` | int | meters |
| `hazard_report_ids` | int[] | active reports affecting this segment |
| `is_synthetic` | bool | `false` — real OpenStreetMap geometry |

```json
{
  "type": "FeatureCollection",
  "osm_timestamp": "2026-10-17T14:11:06Z",
  "features": [
    {
      "type": "Feature",
      "id": 7,
      "geometry": {
        "type": "LineString",
        "coordinates": [[21.4290, 41.9958], [21.4316, 41.9962], [21.4345, 41.9965]]
      },
      "properties": {
        "id": 7,
        "name": "Kej 13 Noemvri",
        "kind": "bike_lane",
        "condition": "red",
        "score": 42,
        "length_m": 460,
        "hazard_report_ids": [101],
        "is_synthetic": false
      }
    }
  ]
}
```

Errors: 400 `invalid_bbox`.

### E10 Bike parking

`GET /api/bike-parking/?bbox=minLng,minLat,maxLng,maxLat` — `bbox` optional, same rules as E3.

GeoJSON `FeatureCollection` of `Point`s: the bicycle parking that already exists in Skopje
(OpenStreetMap). `osm_timestamp` is the OSM snapshot time. Labels and colors come from E2
`bike_parking`.

| property | type | notes |
|---|---|---|
| `id` | int | OpenStreetMap node/way id |
| `name` | string | often `""` |
| `capacity` | int \| null | number of spaces/stands, when tagged |
| `covered` | bool \| null | `null` when not tagged |
| `parking` | string | OSM `parking` value (e.g. `street`, `stands`), `""` if none |
| `access` | string | OSM `access` value, `""` if none |

```json
{
  "type": "FeatureCollection",
  "osm_timestamp": "2026-10-17T14:11:06Z",
  "features": [
    {
      "type": "Feature",
      "id": 3508366301,
      "geometry": {"type": "Point", "coordinates": [21.392381, 42.003979]},
      "properties": {
        "id": 3508366301,
        "name": "",
        "capacity": null,
        "covered": false,
        "parking": "",
        "access": ""
      }
    }
  ]
}
```

Errors: 400 `invalid_bbox`.

### E8 Route scenarios

`GET /api/routes/scenarios/` — no params. Demo origin/destination pairs.

```json
{
  "scenarios": [
    {
      "id": "city-park-to-square",
      "name": "City Park → Macedonia Square",
      "from": {"name": "City Park", "lat": 41.9993, "lng": 21.4180},
      "to": {"name": "Macedonia Square", "lat": 41.9962, "lng": 21.4316}
    }
  ]
}
```

Errors: none expected.

### E9 Route comparison

`GET /api/routes/compare/?scenario=<id>` — `scenario` required (an `id` from E8).

2–3 hand-drawn alternatives, scored by the backend from current reports.

| Field | Type | Notes |
|---|---|---|
| `scenario` | object | Same shape as one item from E8 |
| `recommended_route_id` | string | `id` of the best route |
| `routes[].id` | string | slug |
| `routes[].name` | string | |
| `routes[].geometry` | GeoJSON `LineString` | `[lng, lat]`! Pass to `L.geoJSON()` |
| `routes[].length_m` | int | meters |
| `routes[].score` | int | 0–100, higher = more comfortable |
| `routes[].condition` | enum | `green` \| `amber` \| `red` \| `grey` |
| `routes[].hazards_on_route` | int[] | report ids (fetch details via E4 or reuse E3 data) |
| `routes[].explanation` | string[] | Short, human-readable, ready to display as a list |

`routes` is ordered by `score` descending.

```json
{
  "scenario": {
    "id": "city-park-to-square",
    "name": "City Park → Macedonia Square",
    "from": {"name": "City Park", "lat": 41.9993, "lng": 21.4180},
    "to": {"name": "Macedonia Square", "lat": 41.9962, "lng": 21.4316}
  },
  "recommended_route_id": "park-inner",
  "routes": [
    {
      "id": "park-inner",
      "name": "Through the park",
      "geometry": {
        "type": "LineString",
        "coordinates": [[21.4180, 41.9993], [21.4251, 41.9978], [21.4316, 41.9962]]
      },
      "length_m": 1380,
      "score": 84,
      "condition": "green",
      "hazards_on_route": [102],
      "explanation": [
        "Mostly separated paths",
        "1 informal shortcut (information only)",
        "No fresh hazards reported"
      ]
    },
    {
      "id": "quay-bike-lane",
      "name": "Quay bike lane",
      "geometry": {
        "type": "LineString",
        "coordinates": [[21.4180, 41.9993], [21.4290, 41.9958], [21.4316, 41.9962]]
      },
      "length_m": 1210,
      "score": 46,
      "condition": "red",
      "hazards_on_route": [101],
      "explanation": [
        "Shortest option",
        "Car in bike lane, confirmed by 2 riders, 1 h ago"
      ]
    }
  ]
}
```

Errors: 400 `validation_error` (missing `scenario`), 404 `not_found` (unknown scenario).

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1 | 2026-10-17 | Initial contract | Dimi |
| 2 | 2026-10-17 | Existing bike lanes (E7) and bicycle parking (E10) from OpenStreetMap; E2 gains `segment_kinds` and `bike_parking` | Dimi |
