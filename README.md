# hakaton2026

## Pipeline

**On every commit (pre-commit, local):** large-file check, YAML check, ruff lint + format, gitleaks.

**On every PR (GitHub Actions):**
- `ci.yml`: ruff, bandit, pip-audit, pytest, gitleaks (full history)
- `security-review.yml`: PR Bouncer (Semgrep + Gemini risk score). Needs the `GEMINI_API_KEY` repo secret.
- `pr-bouncer-commands.yml`: lets owners/members/collaborators send PR Bouncer commands as PR comments

## Setup (each teammate)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```
