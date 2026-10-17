# Contributing to BikeAble

Developer notes. To just run the app, see [README.md](README.md).

Cycling road-condition app for Skopje ("Fix My City"): photograph a hazard, Gemini vision
analyzes it, reports show on a map. Mobile-first web app served by Django.

## Team workflow and plans

- Branches, PRs, merge rules, who owns which files: [docs/plan/WORKFLOW.md](docs/plan/WORKFLOW.md)
- API contract between frontend and backend: [docs/plan/API_CONTRACT.md](docs/plan/API_CONTRACT.md)
- Backend plan: [docs/plan/BACKEND_PLAN.md](docs/plan/BACKEND_PLAN.md)
- Frontend notes: [docs/plan/FRONTEND_NOTES.md](docs/plan/FRONTEND_NOTES.md)
- Design: [docs/design/README.md](docs/design/README.md)

## Setup (each teammate)

`make install` creates `.venv`, installs dev dependencies and installs the pre-commit hooks.
Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

The Makefile uses `.venv/bin/` tools when the venv exists, so activating it is optional.
`make help` lists all commands.

## Notes

- **`.env` is optional:** with no `.env` the app runs in dev mode with `AI_MODE=mock`.
- **Gemini key (only for `AI_MODE=live`):** free key from
  [Google AI Studio](https://aistudio.google.com) -> "Get API key", put it in `.env` as
  `GEMINI_API_KEY`, and set `GEMINI_MODEL`. The free tier is rate-limited, so leave
  `AI_MODE=mock` unless you're testing the AI. Tests and CI always use mock.
- **AI photo analysis** lives in the `ai` app; the rest of the app only calls
  `ai.service.analyze_image(bytes, mime_type)`, which returns an `AnalysisResult` or raises
  `AiRateLimited` / `AiUnavailable` (`ai/errors.py`). Prompt text: `ai/prompt.py` (bump
  `PROMPT_VERSION` when you change it). Thresholds for `needs_review`: `ai/schema.py`.
- **Try the AI on one photo:** `make ai-smoke IMG=path/to/photo.jpg` prints the result as JSON
  and which mode was used. In live mode it makes one real API call (uses free-tier quota), so
  never run it in tests or CI. `python manage.py ai_smoke --raw <img>` also prints the full
  model answer.
- **Error screens without a key:** in mock mode set `AI_MOCK_FORCE=rate_limited` or
  `AI_MOCK_FORCE=unavailable` in `.env` to make every analysis fail that way.
- **Phone testing:** `make run` listens on `0.0.0.0:8000`; add the laptop's LAN IP to
  `DJANGO_ALLOWED_HOSTS` in `.env`. Health check: `http://localhost:8000/api/health/`.
- **Demo reports:** `make loaddemo` loads `reports/fixtures/demo_reports.json`: 11 synthetic
  reports around Macedonia Square (`is_synthetic=true`, descriptions start with `[SYNTHETIC]`,
  ids 9001+ so they never overwrite real reports). They have **no photos** yet; demo photos
  come with `feat/demo-data`. Review and verify reports in the admin at `/admin/`.
- **Before pushing:** `make check` runs the same checks as CI (plus Django checks and a
  missing-migrations check).
- **README:** if a change affects how to install, configure or run the app, update
  [README.md](README.md) in the same branch, in the same plain style.

## Pipeline

**On every commit (pre-commit, local):** large-file check, YAML check, ruff lint + format, gitleaks.

**On every PR (GitHub Actions):**
- `ci.yml`: ruff, bandit, pip-audit, pytest, gitleaks (full history)
- `security-review.yml`: PR Bouncer (Semgrep + Gemini risk score). Needs the `GEMINI_API_KEY` repo secret.
- `pr-bouncer-commands.yml`: lets owners/members/collaborators send PR Bouncer commands as PR comments
