# JobPilot: common commands. Run from the project root.
PY := backend/.venv/bin

.PHONY: setup db db-stop migrate facts api web build test

setup:            ## one-time: Python venv + frontend packages
	cd backend && python3.13 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
	cd frontend && npm install --no-fund --no-audit

db:               ## start Postgres (Docker) on localhost:5433
	docker compose -f infra/docker-compose.yml up -d --wait

db-stop:
	docker compose -f infra/docker-compose.yml down

migrate:          ## apply database migrations
	cd backend && .venv/bin/alembic upgrade head

facts:            ## load data/profile_facts.yaml into the database
	cd backend && .venv/bin/python -c "from app.db import session_factory; from app.facts import sync_from_file; from app.config import get_settings; s=session_factory()(); print(sync_from_file(s, get_settings().facts_file)); s.commit()"

api:              ## backend on http://127.0.0.1:8000 (auto-reload)
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web:              ## dashboard dev server on http://localhost:5173
	cd frontend && npm run dev

build:            ## production build of the dashboard (served by the API)
	cd frontend && npm run build

test:             ## backend tests (needs `make db`) + frontend typecheck
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run typecheck
