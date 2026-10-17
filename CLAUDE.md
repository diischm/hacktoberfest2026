# CLAUDE.md

BikeAble — Fix My City hackathon (Skopje). Cyclists photograph road hazards, Gemini analyzes
the photo, reports show on a map. Django 5.2 + DRF backend; mobile-first web app (Django
templates + Leaflet + vanilla JS, no build step). `AI_MODE=mock` by default.

## Rules

- **Before any task, read [docs/plan/WORKFLOW.md](docs/plan/WORKFLOW.md) and
  [docs/plan/API_CONTRACT.md](docs/plan/API_CONTRACT.md).** The contract is the source of truth
  between frontend and backend; don't change it outside its change process.
- **Ownership:** frontend owns only the `web/` app (`web/templates/web/`, `web/static/web/`,
  `web/tests/`). Backend owns everything else, including top-level `templates/` and `tests/`.
  Only edit files your side owns (the one-time exception is in
  [docs/plan/FRONTEND_NOTES.md](docs/plan/FRONTEND_NOTES.md#one-time-shared-edit-frontends-first-pr)).
  Ask first if you're not sure which side you're on.
- Never edit or delete the other side's tests; ask them first.
- For UI work, follow docs/design/README.md and the mockups in docs/design/.
- Run `make check` before finishing; it must be green.
- Never commit secrets or `.env`. Only `.env.example` with placeholders.
- Tests and CI never call the real Gemini API.
- Do not commit or push unless explicitly asked.
