# ── AI Translation Provenance System — Makefile ───────────────────────────────

.PHONY: install run migrate test lint docker-build docker-up docker-down clean frontend-dev demo-dev

## Install Python dependencies
install:
	pip install -r requirements.txt

## Apply database migrations (run once before first `make run`, and after any schema change)
migrate:
	alembic upgrade head

## Run the development server (hot reload) — port 8001, not 8000: see docker-compose.yml's port comment
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

## Run the full test suite (needs Postgres reachable — `make docker-up` first, or point POSTGRES_*/DATABASE_URL at your own)
test:
	PYTHONPATH=. pytest tests/ -v

## Run the Review Shell dev server (frontend/) — proxies /api to :8001
frontend-dev:
	cd frontend && npm run dev

## Run the demo target fixture (frontend/demo-target/) the Review Shell iframes
demo-dev:
	cd frontend/demo-target && npm run dev

## Lint with ruff (install separately: pip install ruff)
lint:
	ruff check app/ tests/

## Build Docker image
docker-build:
	docker build -t ai-provenance-system .

## Start default stack (app + PostgreSQL, mock translation)
docker-up:
	docker-compose up

## Start with persistent vector search (Qdrant)
docker-up-search:
	docker-compose --profile search up

## Start full production stack
docker-up-full:
	docker-compose --profile full up

## Stop all containers
docker-down:
	docker-compose down

## Remove containers and volumes
docker-clean:
	docker-compose down -v

## Open the API docs in browser
docs:
	open http://localhost:8001/docs

## Show project structure
tree:
	find . -not -path '*/__pycache__/*' -not -name '*.pyc' \
	       -not -path '*/.git/*' -not -path '*/node_modules/*' \
	| sort | sed 's|[^/]*/|  |g'

## Clean Python cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
