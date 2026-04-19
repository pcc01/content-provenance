# AI Translation Provenance System

> End-to-end provenance tracking for AI-translated content — built with **FastAPI**, **Haystack**, **XLIFF 2.0**, and **W3C PROV-DM**.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![XLIFF 2.0](https://img.shields.io/badge/XLIFF-2.0%20ISO%2021720-orange.svg)](https://docs.oasis-open.org/xliff/xliff-core/v2.0/)
[![W3C PROV-DM](https://img.shields.io/badge/W3C-PROV--DM%202013-blueviolet.svg)](https://www.w3.org/TR/prov-dm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What It Does

This system answers the key provenance questions for every piece of translated content in your organisation:

| Question | Where it lives |
|----------|---------------|
| **What** was translated? | `SourceText` entity — source text, language, domain |
| **By whom / what?** | `prov:Agent` — AI model + version, or named human translator |
| **How?** | `TranslationMethod` — AI, Human, or Hybrid (AI + human post-edit) |
| **When?** | Activity timestamps — translated_at, reviewed_at, deployed_at |
| **Where is it used?** | `DeploymentRecord` — Website, Banner Ad, Marketing Campaign, Email, Mobile App, Social Media, Print, API |
| **What standard proves it?** | XLIFF 2.0 file with embedded W3C PROV bundle + PROV-JSON / PROV-N exports |

---

## Architecture

![Architecture Diagram](docs/architecture.svg)

```
┌──────────────────────────────────────────────────────────────────┐
│  CLIENTS: Browser Dashboard · TMS/CAT (XLIFF) · API clients      │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTP / REST
┌────────────────────────▼─────────────────────────────────────────┐
│  FASTAPI APPLICATION  (app/main.py)                               │
│  ┌─────────────┐ ┌────────────┐ ┌──────────┐ ┌───────────────┐  │
│  │Translations │ │ Provenance │ │  Search  │ │ XLIFF Export  │  │
│  │ /api/v1/    │ │ /api/v1/   │ │ /api/v1/ │ │  /api/v1/     │  │
│  └──────┬──────┘ └─────┬──────┘ └────┬─────┘ └───────┬───────┘  │
└─────────┼──────────────┼─────────────┼───────────────┼──────────┘
          │              │             │               │
┌─────────▼──────────────▼─────────────▼───────────────▼──────────┐
│  CORE SERVICES                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
│  │  PROV Builder   │  │ Haystack Pipeline│  │   Translation   │ │
│  │ (W3C PROV-DM)   │  │ Semantic + BM25  │  │    Backends     │ │
│  └────────┬────────┘  └────────┬─────────┘  └────────┬────────┘ │
└───────────┼────────────────────┼─────────────────────┼──────────┘
            │  ⇄ bundleId        │                      │
┌───────────▼────────────────────┼──────────────────────▼──────────┐
│  STANDARDS LAYER                                                  │
│  ┌──────────────────────────┐  │  ┌──────────────────────────┐   │
│  │    XLIFF 2.0 Service     │  │  │   W3C PROV-DM Output     │   │
│  │  ISO 21720:2017          │  │  │   PROV-JSON · PROV-N     │   │
│  │  Embeds full PROV bundle │◄─┘  │   Lineage graph          │   │
│  │  per <unit>              │     └──────────────────────────┘   │
│  └──────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────┘
```

### XLIFF ⇄ W3C PROV Integration

This is the core design decision: **every XLIFF `<unit>` is a self-contained provenance artifact**.

```xml
<unit id="abc123" prov:bundleId="bundle:abc123">
  <notes>
    <!-- Core metadata -->
    <note category="provx:translationMethod">ai</note>
    <note category="dc:date">2025-06-01T10:30:00Z</note>

    <!-- W3C PROV Entities -->
    <note category="prov:Entity" id="entity:source:...">
      entityType=SourceText; language=en-US; ...
    </note>
    <note category="prov:Entity" id="entity:translation:...">
      entityType=Translation; targetLanguage=fr-FR; ...
    </note>

    <!-- W3C PROV Activities -->
    <note category="prov:Activity" id="activity:translate:...">
      activityType=Translation; startedAt=...; agentId=...
    </note>

    <!-- W3C PROV Agents -->
    <note category="prov:Agent" id="agent:...">
      name=claude-sonnet-4; agentType=SoftwareAgent; organization=Anthropic
    </note>

    <!-- W3C PROV Relations -->
    <note category="prov:Relation:wasGeneratedBy" id="prov:rel:0:wasGeneratedBy">
      entity=entity:translation:...; activity=activity:translate:...
    </note>
    <note category="prov:Relation:wasAttributedTo" id="prov:rel:1:wasAttributedTo">
      entity=entity:translation:...; agent=agent:...
    </note>

    <!-- Deployment -->
    <note category="provx:deployment" id="dep:...">
      context=banner_ad; location=https://ads.example.com/fr; active=True
    </note>

    <!-- Bundle cross-reference -->
    <note category="prov:Bundle" id="prov:bundleId">bundle:abc123</note>
  </notes>
  <segment state="translated">
    <source dc:language="en-US">Welcome to our platform.</source>
    <target dc:language="fr-FR">Bienvenue sur notre plateforme.</target>
  </segment>
</unit>
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- `pip` or a virtual environment manager

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/ai-translation-provenance.git
cd ai-translation-provenance

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
```

### Run (development — mock translation, in-memory store)

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000 for the dashboard, or http://localhost:8000/docs for the interactive API explorer.

### Run with Anthropic Claude translation

```bash
# Set your key in .env
ANTHROPIC_API_KEY=sk-ant-...
TRANSLATION_PROVIDER=anthropic

uvicorn app.main:app --reload
```

### Run with Docker

```bash
# Default stack (in-memory, mock translation)
docker-compose up

# With persistent Qdrant vector store
docker-compose --profile search up

# Full production stack (Qdrant + PostgreSQL + Elasticsearch)
docker-compose --profile full up
```

---

## API Reference

### Translations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/translations/` | Submit content for translation — returns translation + provenance IDs |
| `GET`  | `/api/v1/translations/` | List all translation units (filter by language, method, status) |
| `GET`  | `/api/v1/translations/{id}` | Get a specific translation unit |
| `POST` | `/api/v1/translations/{id}/deploy` | Record a new deployment location |
| `PUT`  | `/api/v1/translations/{id}/review` | Mark as human-reviewed |
| `GET`  | `/api/v1/translations/stats` | Aggregated statistics |

**POST /api/v1/translations/ — request body**

```json
{
  "source_text": "Welcome to our platform.",
  "source_language": "en-US",
  "target_language": "fr-FR",
  "method": "ai",
  "context": "banner_ad",
  "deployment_location": "https://ads.example.com/campaign/q4",
  "domain": "marketing",
  "translator_name": null
}
```

`method`: `ai` | `human` | `hybrid`  
`context`: `website` | `banner_ad` | `marketing_campaign` | `email` | `mobile_app` | `social_media` | `print` | `api`

### Provenance

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/v1/provenance/{id}` | Full W3C PROV record with entities, activities, agents, relations |
| `GET`  | `/api/v1/provenance/{id}/prov-json` | W3C PROV-JSON serialisation |
| `GET`  | `/api/v1/provenance/{id}/prov-n` | W3C PROV-N human-readable notation |
| `GET`  | `/api/v1/provenance/{id}/lineage` | Lineage graph (nodes + edges for visualisation) |
| `GET`  | `/api/v1/provenance/{id}/deployments` | All deployment records |

### Search (Haystack)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/v1/search/?q={query}` | Semantic or BM25 search over all translations |
| `GET`  | `/api/v1/search/indexed-count` | Number of documents in the vector store |

Query params: `semantic` (bool), `method`, `context`, `top_k`

### XLIFF Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/v1/xliff/{id}` | Download XLIFF 2.0 file with embedded PROV metadata |
| `GET`  | `/api/v1/xliff/{id}/preview` | Preview XLIFF as text |
| `GET`  | `/api/v1/xliff/project/{id}` | Export full project as a single XLIFF document |

---

## Standards Compliance

| Standard | Version | Usage |
|----------|---------|-------|
| [XLIFF](https://docs.oasis-open.org/xliff/xliff-core/v2.0/) | 2.0 (ISO 21720:2017) | Translation exchange format — each unit carries embedded PROV |
| [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) | 2013 | Core provenance data model — Entity, Activity, Agent, Relations |
| [W3C PROV-JSON](https://www.w3.org/Submission/prov-json/) | W3C Submission | JSON serialisation of provenance bundles |
| [W3C PROV-N](https://www.w3.org/TR/prov-n/) | 2013 | Human-readable provenance notation |
| [Dublin Core](http://purl.org/dc/elements/1.1/) | — | `dc:created`, `dc:language`, `dc:date` metadata |
| [BCP-47](https://www.rfc-editor.org/rfc/rfc5646) | — | Language tags (`en-US`, `fr-FR`, etc.) |

### W3C PROV-DM Graph

```
Entity(SourceText)
    │
    │ used ──────────────────────── Activity(Translation)
    │                                      │
    │                               wasAssociatedWith
    │                                      │
    ▼                                  Agent(AI / Human)
Entity(Translation) ◄── wasGeneratedBy ───┘
    │
    ├── wasDerivedFrom ──► Entity(SourceText)
    ├── wasAttributedTo ──► Agent
    │
    │ [if reviewed]
    ├── wasInformedBy ◄── Activity(Review) ◄── wasAssociatedWith ── Agent(Reviewer)
    │
    │ [if deployed]
    └──► Activity(Publication) ──► Entity(DeployedContent)
                                        └── provx:context = website | banner_ad | ...
                                        └── provx:location = URL / campaign ID
```

---

## Translation Backends

Configure via `TRANSLATION_PROVIDER` in `.env`:

| Provider | Env var value | Notes |
|----------|--------------|-------|
| **Mock** | `mock` | Default. Prefixes text with `[LANG]`. No API key needed. |
| **Anthropic Claude** | `anthropic` | Requires `ANTHROPIC_API_KEY`. Uses claude-sonnet-4. |
| **DeepL** | `deepl` | Requires `DEEPL_API_KEY`. Install: `pip install deepl` |
| **Google Translate** | `google` | Requires `GOOGLE_APPLICATION_CREDENTIALS`. |

---

## Development

```bash
# Run tests
make test                       # unit tests (no server)
PYTHONPATH=. pytest tests/ -v   # all tests with pytest

# Lint
pip install ruff
ruff check app/ tests/

# See all make targets
make help
```

---

## Project Structure

```
ai-translation-provenance/
├── app/
│   ├── main.py                     # FastAPI app, lifespan, router registration
│   ├── api/
│   │   ├── translations.py         # Translation CRUD + deploy + review endpoints
│   │   ├── provenance.py           # PROV record, PROV-JSON, PROV-N, lineage
│   │   ├── search.py               # Haystack semantic/BM25 search
│   │   └── xliff_export.py         # XLIFF 2.0 download and preview
│   ├── core/
│   │   ├── config.py               # Environment-based settings
│   │   ├── database.py             # In-memory store (swap for PostgreSQL)
│   │   ├── prov_builder.py         # W3C PROV-DM graph builder + PROV-JSON
│   │   ├── haystack_pipeline.py    # Haystack 2.x indexing and search
│   │   └── translation_backends.py # Pluggable: Mock / Anthropic / DeepL / Google
│   ├── models/
│   │   └── schemas.py              # Pydantic models (PROV, XLIFF, Translation, Deployment)
│   └── xliff/
│       └── xliff_service.py        # XLIFF 2.0 generation with full embedded PROV
├── docs/
│   └── architecture.svg            # System architecture diagram
├── frontend/
│   └── index.html                  # Single-file dashboard (Translate/Provenance/Search/XLIFF)
├── tests/
│   ├── conftest.py                 # pytest fixtures, async client
│   ├── test_provenance.py          # Unit tests (models, XLIFF, PROV builder, DB)
│   └── test_api.py                 # API integration tests (all endpoints)
├── .env.example                    # Environment variable reference
├── .gitignore
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml              # dev / search / full profiles
├── LICENSE                         # MIT
├── Makefile
├── pyproject.toml                  # packaging + pytest + ruff config
├── README.md
├── ROADMAP.md
└── requirements.txt
```

---

## License

MIT — see [LICENSE](LICENSE).
