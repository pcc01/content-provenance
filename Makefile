# ── AI Translation Provenance System — Makefile ───────────────────────────────

.PHONY: install run test lint docker-build docker-up docker-down clean

## Install Python dependencies
install:
	pip install -r requirements.txt

## Run the development server (hot reload)
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Run the test suite
test:
	PYTHONPATH=. python tests/test_provenance.py

## Run with pytest (if installed)
pytest:
	PYTHONPATH=. pytest tests/ -v

## Lint with ruff (install separately: pip install ruff)
lint:
	ruff check app/ tests/

## Build Docker image
docker-build:
	docker build -t ai-provenance-system .

## Start default stack (in-memory, mock translation)
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
	open http://localhost:8000/docs

## Show project structure
tree:
	find . -not -path '*/__pycache__/*' -not -name '*.pyc' \
	       -not -path '*/.git/*' -not -path '*/node_modules/*' \
	| sort | sed 's|[^/]*/|  |g'

## Clean Python cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
