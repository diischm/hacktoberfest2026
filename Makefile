# Developer shortcuts. Run `make help` to list them.
# Uses .venv/bin/ tools when the venv exists, otherwise whatever is on PATH (e.g. in CI).
BIN := $(if $(wildcard .venv/bin/python),.venv/bin/,)
PYTHON := $(BIN)python

.PHONY: help install run migrate loaddemo superuser ai-smoke check lint security test django-check

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Create .venv, install dev dependencies, install git hooks
	test -d .venv || python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pre-commit install

run: ## Start dev server reachable from phones on the same Wi-Fi
	$(PYTHON) manage.py runserver 0.0.0.0:8000

migrate: ## Apply database migrations
	$(PYTHON) manage.py migrate

loaddemo: ## Load synthetic demo reports (ids 9001+, no photos); safe to re-run
	$(PYTHON) manage.py loaddata demo_reports

superuser: ## Create an admin login for /admin/
	$(PYTHON) manage.py createsuperuser

ai-smoke: ## Analyze one photo and print the result: make ai-smoke IMG=photo.jpg (live = 1 real call)
	@test -n "$(IMG)" || { echo "Usage: make ai-smoke IMG=path/to/photo.jpg"; exit 1; }
	$(PYTHON) manage.py ai_smoke "$(IMG)"

check: lint security django-check test ## Run everything CI runs (except gitleaks: that's in pre-commit)

lint: ## ruff lint + format check (same as CI)
	$(BIN)ruff check .
	$(BIN)ruff format --check .

security: ## bandit + pip-audit (same as CI)
	$(BIN)bandit -c pyproject.toml -r . -x './.venv,./tests,*/tests/*'
	$(BIN)pip-audit -r requirements-dev.txt

django-check: ## Django system checks + fail on missing migrations
	$(PYTHON) manage.py check
	$(PYTHON) manage.py makemigrations --check --dry-run

test: ## Run pytest (same as CI)
	$(BIN)pytest -v
