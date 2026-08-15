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

## Testing the Strapi Integration

The CMS integration (`app/core/integrations/strapi.py`, `POST /api/v1/
integrations/cms/push`) needs a real Strapi instance to test against
end-to-end — `docker-compose --profile cms` runs one locally, and
`scripts/bootstrap_strapi.py` sets it up completely from the command line
(admin account, a demo content type, an API token, one demo entry — no
clicking through Strapi's admin UI required):

```bash
docker-compose --profile cms up -d --build strapi   # first run builds a real Strapi project — a few minutes
python scripts/bootstrap_strapi.py                   # prints STRAPI_BASE_URL / STRAPI_API_TOKEN to add to .env
```

Add the printed values to `.env`, restart the app, then push a real
translation into the demo entry it created:

```bash
curl -X POST localhost:8001/api/v1/integrations/cms/push -H "Content-Type: application/json" -d '{
  "unit_id": "<a translation_unit_id from POST /api/v1/translations/>",
  "provider": "strapi", "content_type": "translation-examples",
  "entry_id": "<printed by the bootstrap script>", "field_name": "body"
}'
```

**Sample website** (`demo/strapi-site/index.html`, served by the app at
`http://localhost:8001/demo/`): a plain page that reads its copy straight
from Strapi's public REST API — no token in the page, just the demo
content type's public `find`/`findOne` permissions (granted automatically
by the bootstrap script). Every entry it lists shows the CMS's live text
plus, once you've pushed at least once, a "Provenance recorded" panel
with the summary/agent/method/confidence and a link to the full W3C PROV
record. Push a translation as above, then refresh the page — it updates
live, no rebuild/redeploy step, which is the actual point of storing
provenance on the CMS entry itself rather than only in this system.

Or run the whole thing — including the push and reading the entry back
from Strapi to confirm both the translated text and the `content_
provenance` field actually landed — in one shot:

```bash
python scripts/bootstrap_strapi.py --verify   # needs the app running at localhost:8001
```

Note on the Docker image: Strapi has no official ready-to-run Docker Hub
image, and the best-known community replacement (`naskio/strapi`) was
found broken while building this integration ("Cannot find module
'react'" during its internal build step, reproduced against several
tags). `docker/strapi/Dockerfile` instead generates a real project via
`create-strapi-app` at image-build time — see that file's comment for
details. The automated test suite (`tests/test_cms_integration.py`) does
**not** need any of this — it monkeypatches the `CMSIntegration` factory
with an offline stub, same convention as the scorer/translation-backend
tests.

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
