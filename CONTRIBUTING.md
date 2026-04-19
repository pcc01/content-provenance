# Contributing

Thank you for your interest in contributing to the AI Translation Provenance System.

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/ai-translation-provenance.git
cd ai-translation-provenance
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # edit as needed
uvicorn app.main:app --reload # http://localhost:8000
```

## Running Tests

```bash
# Unit tests only (no server needed)
PYTHONPATH=. pytest tests/test_provenance.py -v

# Full API integration tests
PYTHONPATH=. pytest tests/test_api.py -v

# All tests
PYTHONPATH=. pytest -v
```

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
