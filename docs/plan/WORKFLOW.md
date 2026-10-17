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

> To be filled in by the frontend developer (branches, milestones, what's on mocks).
> Must follow [API_CONTRACT.md](API_CONTRACT.md) and [FRONTEND_NOTES.md](FRONTEND_NOTES.md).
