# DayFlow developer commands. Run `make help` for the list.
#
# Everything assumes the backend venv lives at backend/.venv. `make setup`
# creates it.

SHELL := /bin/bash
PY    := backend/.venv/bin/python
PIP   := backend/.venv/bin/pip

# Local development runs against SQLite with fail-closed settings relaxed.
# Production settings refuse to start without a real secret key, host list,
# CORS allowlist, Postgres and Redis -- see docs/CONFIGURATION.md.
DEV_ENV := DJANGO_DEBUG=true \
           DJANGO_ALLOW_SQLITE=true \
           DJANGO_SECRET_KEY=local-development-only \
           DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
           DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:8080 \
           DATABASE_URL=

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend migrate makemigrations seed \
        superuser backend frontend dev test test-backend test-frontend \
        typecheck lint audit check build desktop-win desktop-win-zip desktop-linux \
        clean docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- setup -----------------------------------------------------------------

setup: setup-backend setup-frontend ## Install backend and frontend dependencies

setup-backend: ## Create the venv and install Python dependencies
	python3 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@test -f backend/.env || (cp backend/.env.example backend/.env && \
		echo "Created backend/.env from the example -- fill it in before deploying.")

setup-frontend: ## Install frontend dependencies
	cd frontend && npm install

# ---- database --------------------------------------------------------------

migrate: ## Apply database migrations
	cd backend && $(DEV_ENV) ../$(PY) manage.py migrate

makemigrations: ## Generate migrations for model changes
	cd backend && $(DEV_ENV) ../$(PY) manage.py makemigrations

seed: ## Create the default USD subscription plans
	cd backend && $(DEV_ENV) ../$(PY) manage.py seed_plans

superuser: ## Create a Django admin superuser
	cd backend && $(DEV_ENV) ../$(PY) manage.py createsuperuser

# ---- running ---------------------------------------------------------------

backend: ## Run the API on :8000
	cd backend && $(DEV_ENV) ../$(PY) manage.py runserver 8000

frontend: ## Run the SPA on :8080
	cd frontend && npm run dev

dev: ## Reminder of how to run both halves
	@echo "Run these in two terminals:"
	@echo "  make backend    # API   -> http://localhost:8000"
	@echo "  make frontend   # app   -> http://localhost:8080"

# ---- quality ---------------------------------------------------------------

test: test-backend test-frontend ## Run every test

test-backend: ## Run the Django test suite (uses core.settings_test)
	cd backend && ../$(PY) manage.py test

audit: ## Run only the security regression suite
	cd backend && ../$(PY) manage.py test core.tests_poc -v2

typecheck: ## Typecheck the frontend
	cd frontend && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json

lint: ## Lint the frontend
	cd frontend && npm run lint

test-frontend: typecheck ## Frontend checks

check: ## Django system checks, including the deployment checklist
	cd backend && $(DEV_ENV) ../$(PY) manage.py check
	cd backend && DJANGO_SETTINGS_MODULE=core.settings_test ../$(PY) manage.py check --deploy || true

build: ## Build the production frontend bundle
	cd frontend && npm run build

desktop-win: ## Build the Windows desktop app (installer + portable + zip; needs Wine on Linux)
	cd frontend && npm run electron:build:win

desktop-win-zip: ## Build the Windows desktop app, zip only (no Wine required)
	cd frontend && npm run electron:build:win:zip

desktop-linux: ## Build the Linux AppImage
	cd frontend && npm run electron:build:linux

# ---- docker ----------------------------------------------------------------

docker-up: ## Start the full stack in Docker
	docker compose up --build

docker-down: ## Stop the stack and remove volumes
	docker compose down -v

clean: ## Remove build artefacts and caches
	rm -rf frontend/dist backend/staticfiles
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
