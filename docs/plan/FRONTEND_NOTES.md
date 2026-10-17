# Frontend notes (from the backend side)

What the frontend needs to know about the backend. This is **not** the frontend plan —
the frontend developer writes that in [WORKFLOW.md](WORKFLOW.md#frontend-plan).

## Ownership

Frontend owns **only the `web/` Django app**. It renders pages; no models, no API.

| Path | Owner |
|---|---|
| `web/views.py`, `web/urls.py`, `web/apps.py`, `web/__init__.py` | Frontend |
| `web/templates/web/...` (e.g. `web/templates/web/map.html`) | Frontend |
| `web/static/web/...` (e.g. `web/static/web/js/app.js`, `web/static/web/mock/meta.json`) | Frontend |
| `web/tests/` | Frontend |
| Everything else, incl. top-level `templates/` (`templates/home.html`), `config/`, `reports/`, `ai/`, `routes/`, `tests/`, `requirements*.txt`, `pyproject.toml`, `Makefile`, CI | Backend |

- The extra `web/` level inside `templates/` and `static/` is a namespace: Django merges all
  apps' template and static folders, so `web/...` names can't collide with another app's files.
- **No settings change is needed to find these files.** `config/settings.py` has
  `"APP_DIRS": True` (Django looks in each installed app's `templates/` folder) and doesn't
  override `STATICFILES_FINDERS`, so the default `AppDirectoriesFinder` serves each installed
  app's `static/` folder. Both just need `"web"` in `INSTALLED_APPS`.
- Reference files with their namespace: `render(request, "web/map.html")`,
  `{% static 'web/js/app.js' %}`.

Need a Python package or a settings change? Ask backend; don't edit those files.

## One-time shared edit (frontend's first PR)

The **only** edits outside `web/`, allowed once, announced in chat when the PR opens:

| File | Change |
|---|---|
| `config/settings.py` | add `"web",` to `INSTALLED_APPS` |
| `config/urls.py` | replace the placeholder `path("", views.home, name="home"),` with `path("", include("web.urls")),` (add `include` to the `django.urls` import) |

Nothing else outside `web/`. Top-level `templates/home.html` and the `home` view in
`config/views.py` stay as they are; backend deletes them afterwards. The home-page test
handoff is in [WORKFLOW.md](WORKFLOW.md#handoffs).

## Mock data

- Keep mock responses in `web/static/web/mock/*.json` (served at `/static/web/mock/...`).
  File names are listed in the [endpoint table](API_CONTRACT.md#endpoints). Content =
  **exactly** the contract examples (copy-paste; extra features are fine as long as the shape is identical).
- One JS config switch, per endpoint, e.g. in `web/static/web/js/config.js`:

  ```js
  // "mock" = read /static/web/mock/*.json, "live" = call /api/...
  const API_MODE = {
    meta: "mock", reports: "mock", reportDetail: "mock", createReport: "mock",
    feedback: "mock", segments: "mock", scenarios: "mock", compare: "mock",
  };
  ```

- Mock POSTs: return the mock file after a fake delay (~2–5 s) so the loading state gets tested.
- Also mock the 429 error case (`web/static/web/mock/error-ai-rate-limited.json`, from the E5 example).
- When backend announces a milestone, flip only the listed keys to `"live"`.

## Map

| Topic | Note |
|---|---|
| Library | Leaflet + OpenStreetMap tiles (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`), attribution "© OpenStreetMap contributors" is required |
| Demo area | From `GET /api/meta/` → `map.center` / `map.zoom` / `map.bounds`. Placeholder: Macedonia Square, `lat 41.9962, lng 21.4316`, zoom 15 (to be confirmed) |
| **Coordinate order** | GeoJSON = `[lng, lat]`; Leaflet = `[lat, lng]`. Use `L.geoJSON()` for API geometry. See [Conventions](API_CONTRACT.md#conventions) |
| bbox | `map.getBounds().toBBoxString()` is already in the API's `bbox` order |
| Colors/labels | From `GET /api/meta/`, not hardcoded |
| Synthetic data | `is_synthetic: true` must show a visible "Demo data" label |
| `informal_shortcut` | Information, not a hazard (`is_hazard: false` in meta) |

## Upload

| Topic | Note |
|---|---|
| Camera | `<input type="file" accept="image/*" capture="environment">` — works over plain http |
| Location | User taps the map. GPS optional: browsers block `navigator.geolocation` on `http://192.168.x.x` (needs https or localhost) |
| Limits | From `meta.upload`: JPEG/PNG/WebP, ≤ 10 MB, note ≤ 500 chars |
| Slow request | E5 can take ~15 s: show loading, disable submit, timeout ≥ 30 s |
| Errors | Branch on `error.code` (see [Error format](API_CONTRACT.md#error-format)); show `error.message`; `fields` for inline form errors |
| Optional | Resizing in the browser (canvas → JPEG ~1600 px) makes uploads faster and drops EXIF/GPS; backend works either way |

## CSRF

Django rejects POSTs without a CSRF token (403 `csrf_failed`). For every POST:

1. The page template renders the token once: `{% csrf_token %}` (anywhere in `<body>`).
2. JS reads it and sends it as a header:

```js
const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;

// JSON (feedback)
fetch(`/api/reports/${id}/feedback/`, {
  method: "POST",
  headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
  body: JSON.stringify({action: "still_there"}),
});

// multipart (upload): do NOT set Content-Type, the browser adds the boundary
const form = new FormData();
form.append("photo", file); form.append("lat", lat); form.append("lng", lng);
fetch("/api/reports/", {method: "POST", headers: {"X-CSRFToken": csrf}, body: form});
```

Same origin only (page and API on the same host:port) — no CORS is configured.

## Photos, static files, PWA

| Topic | Note |
|---|---|
| Uploaded photos | Served from `MEDIA_URL` (`/media/...`) **only when `DJANGO_DEBUG=true`**. Use `photo_url` as-is; it may be `null` |
| Static files | `{% load static %}` + `{% static 'web/js/app.js' %}`; no JS build step |
| Service worker | Must be served from `/` scope (e.g. `/sw.js` via a `web` view), not `/static/`, or it can't control pages. Service workers only run on https or `localhost`, so on a phone over `http://<LAN-IP>:8000` the app works but won't install/cache offline |
| API base | Relative URLs (`/api/...`) — works on localhost and LAN IPs |
