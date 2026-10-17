# hakaton2026 — BikeAble

Cycling road-condition app for Skopje ("Fix My City"): photograph a hazard, Gemini vision
analyzes it, reports show on a map. Mobile-first web app served by Django.

## Quick start

```bash
git clone <repo-url> && cd hakaton2026
make install                 # creates .venv, installs dev deps, installs pre-commit hooks
source .venv/bin/activate
cp .env.example .env         # optional: the app runs without it (AI_MODE=mock)
make migrate
make loaddemo                # optional: synthetic demo reports for the map/admin
make superuser               # optional: login for http://localhost:8000/admin/
make run                     # http://localhost:8000  and  http://localhost:8000/api/health/
```

- **Gemini key (only for `AI_MODE=live`):** get a free key at
  [Google AI Studio](https://aistudio.google.com) -> "Get API key", put it in `.env` as
  `GEMINI_API_KEY`, and set `GEMINI_MODEL`. The free tier is rate-limited, so leave
  `AI_MODE=mock` unless you're testing the AI. Tests and CI always use mock.
- **Open it on your phone:** find your laptop's LAN IP (`hostname -I`), add it to
  `DJANGO_ALLOWED_HOSTS` in `.env`, run `make run`, open `http://<ip>:8000` on a phone on the
  same Wi-Fi.
- **Demo reports:** `make loaddemo` loads `reports/fixtures/demo_reports.json`: 11 synthetic
  reports around Macedonia Square (`is_synthetic=true`, descriptions start with `[SYNTHETIC]`,
  ids 9001+ so they never overwrite real reports). They have **no photos** yet; demo photos
  come with `feat/demo-data`. Review and verify reports in the admin at `/admin/`.
- **Before pushing:** `make check` runs the same checks as CI (plus Django checks and a
  missing-migrations check). `make help` lists all commands.

## Pipeline

**On every commit (pre-commit, local):** large-file check, YAML check, ruff lint + format, gitleaks.

**On every PR (GitHub Actions):**
- `ci.yml`: ruff, bandit, pip-audit, pytest, gitleaks (full history)
- `security-review.yml`: PR Bouncer (Semgrep + Gemini risk score). Needs the `GEMINI_API_KEY` repo secret.
- `pr-bouncer-commands.yml`: lets owners/members/collaborators send PR Bouncer commands as PR comments

## Setup (each teammate)

`make install` (or manually):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```
