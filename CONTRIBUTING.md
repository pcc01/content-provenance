# Contributing

Thank you for your interest in contributing to the AI Translation Provenance System.

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/ai-translation-provenance.git
cd ai-translation-provenance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium        # only needed for Phase 8's "review any URL" fetch mode
cp .env.example .env               # edit as needed
docker-compose up -d postgres      # or point .env at your own Postgres
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

For the review UI, see the "Run the review environment" section of the
[README](README.md#run-the-review-environment-review-shell) — it's a
separate Vite+React app under `frontend/`.

## Running Tests

Every test needs Postgres reachable — `docker-compose up -d postgres` first
(the schema is dropped and recreated once per test session, so this can be
the same instance you use for development):

```bash
PYTHONPATH=. pytest -v                        # everything
PYTHONPATH=. pytest tests/test_api.py -v      # one file
```

Frontend changes: `cd frontend && npx tsc -b` (and `frontend/demo-target`)
for type-checking — there's no automated frontend test suite yet, so verify
UI changes by actually running the dev servers and using the feature in a
browser.

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting:

```bash
pip install ruff
ruff check app/ tests/
ruff format app/ tests/
```

## Pull Request Guidelines

1. Fork the repo and create a feature branch: `git checkout -b feat/my-feature`
2. Write tests for new functionality — see `tests/` for patterns
3. Ensure all tests pass and `ruff check` is clean
4. Update `ROADMAP.md` if your PR completes a planned item
5. Open a PR with a clear description of what changed and why

## Standards This Project Follows

- **W3C PROV-DM** — all provenance records must conform to https://www.w3.org/TR/prov-dm/
- **XLIFF 2.0** — translation exchange format must conform to ISO 21720:2017
- **BCP-47** — all language tags must be valid BCP-47 codes
- **Semantic versioning** — `MAJOR.MINOR.PATCH`

## Reporting Issues

Please open a GitHub issue with:
- A clear description of the bug or feature request
- Steps to reproduce (for bugs)
- Expected vs actual behaviour
- Python version, OS, relevant dependency versions
