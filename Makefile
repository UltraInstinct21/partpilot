# PartPilot - task runner
#
#   make test      run the backend and frontend test suites
#   make lint      run ruff, black, eslint and prettier
#   make run-api   start the FastAPI backend on 127.0.0.1:8000
#   make run-web   start the Vite frontend on 127.0.0.1:5173
#   make mock-api  start the fixture backed mock API on 127.0.0.1:8001
#
# Every target works from a clean checkout after `make setup`.

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python
PIP := $(BACKEND)/.venv/bin/pip
UV := uv

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend test test-backend test-frontend \
        lint lint-backend lint-frontend format format-backend format-frontend \
        run-api run-web mock-api types clean seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup ----

setup: setup-backend setup-frontend ## Install backend and frontend dependencies

setup-backend: ## Create the backend virtualenv and install dependencies
	cd $(BACKEND) && $(UV) sync --python 3.12
	@echo "backend ready: $(BACKEND)/.venv"

setup-frontend: ## Install the frontend dependencies
	cd $(FRONTEND) && npm install --no-audit --no-fund
	@echo "frontend ready: $(FRONTEND)/node_modules"

# ----------------------------------------------------------------- test ----

test: test-backend test-frontend test-eval ## Run every test suite

test-backend: ## Run the backend pytest suite
	cd $(BACKEND) && .venv/bin/python -m pytest

test-frontend: ## Run the frontend vitest suite
	cd $(FRONTEND) && npm run test

test-eval: ## Run the evaluation harness test suite
	cd $(BACKEND) && .venv/bin/python -m pytest ../eval -q

# ----------------------------------------------------------------- lint ----

lint: lint-backend lint-frontend lint-eval ## Run every linter

lint-backend: ## ruff + black --check
	cd $(BACKEND) && .venv/bin/python -m ruff check .
	cd $(BACKEND) && .venv/bin/python -m black --check .

lint-frontend: ## eslint + prettier --check
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run format:check

lint-eval: ## ruff + black --check on the evaluation harness
	$(PY) -m ruff check eval
	$(PY) -m black --check eval

# --------------------------------------------------------------- format ----

format: format-backend format-frontend format-eval ## Auto-format the code

format-backend:
	cd $(BACKEND) && .venv/bin/python -m ruff check --fix . && .venv/bin/python -m black .

format-frontend:
	cd $(FRONTEND) && npm run format

format-eval:
	$(PY) -m ruff check --fix eval && $(PY) -m black eval

# ------------------------------------------------------------------ run ----

run-api: ## Start the FastAPI backend
	cd $(BACKEND) && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run-web: ## Start the Vite frontend
	cd $(FRONTEND) && npm run dev

mock-api: ## Start the fixture backed mock API on port 8001
	cd $(BACKEND) && .venv/bin/python tools/mock_api.py

# ---------------------------------------------------------------- misc ----

types: ## Regenerate frontend/src/api/types.ts from contracts/openapi.yaml
	cd $(FRONTEND) && npm run gen:api

seed: ## Load the seed data into the SQLite database
	cd $(BACKEND) && .venv/bin/python -m db.seed

clean: ## Remove build artefacts and caches
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(FRONTEND)/dist $(FRONTEND)/coverage
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
