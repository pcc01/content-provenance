# Roadmap

Status legend: ✅ Built · 🔧 Partial · 📋 Planned · 💡 Suggested

---

## v1.0 — Current Build

### Core Provenance Engine

| Feature | Status | Notes |
|---------|--------|-------|
| W3C PROV-DM data model (Entity / Activity / Agent) | ✅ | `app/models/schemas.py` |
| All six PROV relations (wasGeneratedBy, wasDerivedFrom, wasAttributedTo, used, wasAssociatedWith, wasInformedBy) | ✅ | `app/core/prov_builder.py` |
| PROV-JSON serialisation (W3C Submission) | ✅ | `GET /api/v1/provenance/{id}/prov-json` |
| PROV-N human-readable notation | ✅ | `GET /api/v1/provenance/{id}/prov-n` |
| Provenance bundle per translation unit with XLIFF cross-reference (`xliff_document_id`) | ✅ | `ProvenanceRecord.xliff_document_id` |
| Lineage graph output (nodes + edges) for visualisation | ✅ | `GET /api/v1/provenance/{id}/lineage` |
| Review workflow: human post-edit creates new PROV Activity + Agent | ✅ | `PUT /api/v1/translations/{id}/review` |
| Deployment provenance (Publication activity + DeployedContent entity) | ✅ | `POST /api/v1/translations/{id}/deploy` |

### XLIFF 2.0

| Feature | Status | Notes |
|---------|--------|-------|
| XLIFF 2.0 document generation (ISO 21720:2017) | ✅ | `app/xliff/xliff_service.py` |
| Full W3C PROV bundle embedded in every `<unit>` | ✅ | All entities, activities, agents, relations as `<note>` elements |
| `prov:bundleId` cross-reference on `<xliff>` and `<unit>` | ✅ | Links back to `/provenance/{id}/prov-json` |
| BCP-47 language tags on `<source>` and `<target>` | ✅ | `dc:language` attribute |
| Dublin Core metadata (created, date, language) | ✅ | `dc:created`, `dc:date` |
| Custom `provx:` namespace (confidence, quality, deployment) | ✅ | `urn:ai-provenance:xliff-ext:1.0` |
| XLIFF state mapping (initial / translated / reviewed / final) | ✅ | `_xliff_state()` |
| XLIFF document parser (reconstruct PROV from `<note>` elements) | ✅ | `parse_xliff_document()` |
| Single-unit XLIFF export | ✅ | `GET /api/v1/xliff/{id}` |
| Project-level XLIFF export (all units in one document) | ✅ | `GET /api/v1/xliff/project/{id}` |

### Translation

| Feature | Status | Notes |
|---------|--------|-------|
| Pluggable translation backend abstraction | ✅ | `app/core/translation_backends.py` |
| Mock backend (dev/test, no API key) | ✅ | Default via `TRANSLATION_PROVIDER=mock` |
| Anthropic Claude backend | ✅ | `TRANSLATION_PROVIDER=anthropic` |
| DeepL backend | ✅ | `TRANSLATION_PROVIDER=deepl` |
| Google Cloud Translate backend | ✅ | `TRANSLATION_PROVIDER=google` |
| AI translation method tracking | ✅ | `TranslationMethod.AI` → `SoftwareAgent` |
| Human translation method tracking | ✅ | `TranslationMethod.HUMAN` → `Person` |
| Hybrid (AI + human post-edit) tracking | ✅ | `TranslationMethod.HYBRID` |

### Deployment Context Tracking

| Feature | Status | Notes |
|---------|--------|-------|
| Website | ✅ | `DeploymentContext.WEBSITE` |
| Banner Ad | ✅ | `DeploymentContext.BANNER_AD` |
| Marketing Campaign | ✅ | `DeploymentContext.MARKETING_CAMPAIGN` |
| Email | ✅ | `DeploymentContext.EMAIL` |
| Mobile App | ✅ | `DeploymentContext.MOBILE_APP` |
| Social Media | ✅ | `DeploymentContext.SOCIAL_MEDIA` |
| Print | ✅ | `DeploymentContext.PRINT` |
| API | ✅ | `DeploymentContext.API` |
| Multiple deployment records per translation | ✅ | Each gets its own PROV `Publication` activity |
| Deployment retirement / inactive tracking | ✅ | `DeploymentRecord.is_active`, `retired_at` |

### Search (Haystack)

| Feature | Status | Notes |
|---------|--------|-------|
| Haystack 2.x integration | ✅ | `app/core/haystack_pipeline.py` |
| In-memory document store | ✅ | Default |
| Sentence-Transformers embedding (all-MiniLM-L6-v2) | ✅ | Semantic search |
| BM25 keyword search fallback | ✅ | When Haystack unavailable or `semantic=false` |
| Filter by translation method | ✅ | `?method=ai|human|hybrid` |
| Filter by deployment context | ✅ | `?context=banner_ad|website|…` |
| Filter by language pair | ✅ | `?source_language=en-US&target_language=fr-FR` |
| Qdrant persistent vector store | 🔧 | Config present, needs `--profile search` |
| Elasticsearch document store | 🔧 | Config present, needs `--profile full` |

### API & Infrastructure

| Feature | Status | Notes |
|---------|--------|-------|
| FastAPI application with async lifespan | ✅ | `app/main.py` |
| CORS middleware | ✅ | Configurable via `CORS_ORIGINS` |
| Environment-based config (`.env`) | ✅ | `app/core/config.py` |
| In-memory database (dev) | ✅ | `app/core/database.py` |
| Dockerfile | ✅ | Python 3.12-slim, model pre-download |
| Docker Compose (dev / search / full profiles) | ✅ | `docker-compose.yml` |
| Makefile with common tasks | ✅ | `make run`, `make test`, `make docker-up` |
| pyproject.toml (packaging + pytest + ruff) | ✅ | |
| `.gitignore` | ✅ | Python, venv, secrets, ML models |
| MIT License | ✅ | |
| CONTRIBUTING.md | ✅ | |

### Frontend Dashboard

| Feature | Status | Notes |
|---------|--------|-------|
| Translate tab (submit + result display) | ✅ | `frontend/index.html` |
| W3C PROV chain visualisation (post-translate) | ✅ | Entity → Activity → Agent → Deployment |
| History tab (list all translations) | ✅ | |
| Provenance tab (lookup + PROV-N + PROV-JSON display) | ✅ | |
| Search tab (Haystack query UI) | ✅ | |
| XLIFF tab (preview + download) | ✅ | |
| Stats bar (totals by method / status / deployments) | ✅ | |

### Tests

| Feature | Status | Notes |
|---------|--------|-------|
| Unit tests — models | ✅ | `tests/test_provenance.py` |
| Unit tests — XLIFF generation + round-trip parse | ✅ | |
| Unit tests — W3C PROV builder | ✅ | |
| Unit tests — database CRUD | ✅ | |
| API integration tests — translations | ✅ | `tests/test_api.py` |
| API integration tests — provenance (PROV, PROV-N, PROV-JSON, lineage) | ✅ | |
| API integration tests — XLIFF export | ✅ | |
| API integration tests — search | ✅ | |
| pytest-asyncio config in pyproject.toml | ✅ | `asyncio_mode = "auto"` |

---

## v1.1 — Planned Next

### Persistence

| Feature | Status | Notes |
|---------|--------|-------|
| PostgreSQL backend (asyncpg + SQLAlchemy 2.x) | 📋 | Replace in-memory store for production |
| pgvector for embedding storage alongside translations | 📋 | Eliminates separate vector store in simple deployments |
| Database migrations (Alembic) | 📋 | Schema versioning |

### XLIFF Enhancements

| Feature | Status | Notes |
|---------|--------|-------|
| XLIFF 2.0 `<matches>` module (translation memory hits) | 📋 | Leverage existing TM for provenance |
| XLIFF import — ingest external XLIFF with PROV extraction | 📋 | Accept XLIFF from external TMS |
| XLIFF `<glossary>` module support | 📋 | Terminology tracking |
| XLIFF validation against official NVDL schema | 📋 | Strict conformance check |

### Provenance Enhancements

| Feature | Status | Notes |
|---------|--------|-------|
| PROV-XML serialisation | 📋 | W3C alternate serialisation for RDF/linked-data tooling |
| PROV-O (OWL ontology) export | 📋 | Semantic web / linked open data interoperability |
| Machine-readable provenance certificate (signed JSON-LD) | 📋 | Cryptographic attestation of AI involvement |
| Provenance diff — compare two versions of a translation | 📋 | `wasDerivedFrom` chain traversal |
| Bulk provenance export (all units in a project) | 📋 | PROV-JSON archive |

### Quality & Review

| Feature | Status | Notes |
|---------|--------|-------|
| MQM (Multidimensional Quality Metrics) scoring | 📋 | Structured error annotation |
| BLEU / chrF automatic quality estimation | 📋 | For AI translations |
| Review assignment queue | 📋 | Route AI translations to human reviewers |
| Version history per translation unit | 📋 | Full edit history with PROV `wasRevisionOf` |

---

## v1.2 — Suggested (Not Yet Built)

_These features were discussed in the design phase but not yet implemented._

### TMS Integration

| Feature | Status | Notes |
|---------|--------|-------|
| Phrase (Memsource) API connector | 💡 | Bi-directional XLIFF exchange |
| Lokalise API connector | 💡 | Push/pull translations with provenance |
| Transifex API connector | 💡 | |
| SDL Trados plugin concept | 💡 | CAT tool provenance injection |

### AI Act & Regulatory Compliance

| Feature | Status | Notes |
|---------|--------|-------|
| EU AI Act risk classification per translation | 💡 | Flag high-risk use cases by deployment context |
| AI transparency disclosure generator | 💡 | Auto-generate "translated by AI" disclosures for regulated contexts |
| Audit log export (CSV / XLSX) | 💡 | Compliance reporting for legal/procurement |
| GDPR data subject export | 💡 | Export all provenance records for a given user |
| Data retention policy enforcement | 💡 | Auto-expire / anonymise old records |

### Analytics & Reporting

| Feature | Status | Notes |
|---------|--------|-------|
| Translation volume dashboard (by language pair, method, context) | 💡 | Visual analytics |
| Cost tracking (per-word rates by provider) | 💡 | Connect to billing APIs |
| Quality trend over time | 💡 | MQM scores plotted per project |
| Agent performance report (AI vs human confidence/quality) | 💡 | |

### Multi-Tenancy & Auth

| Feature | Status | Notes |
|---------|--------|-------|
| API key authentication | 💡 | Per-tenant access control |
| OAuth2 / JWT support | 💡 | Enterprise SSO integration |
| Organisation / project namespacing | 💡 | Isolate provenance records per client |
| Role-based access control (RBAC) | 💡 | PM / reviewer / admin roles |

### Additional Search

| Feature | Status | Notes |
|---------|--------|-------|
| Search by agent (find all translations by a specific AI model) | 💡 | `?agent=claude-sonnet-4` |
| Search by date range | 💡 | `?from=2025-01-01&to=2025-06-30` |
| Similarity search (find near-duplicates) | 💡 | Deduplication before sending to MT |
| Search within PROV relations | 💡 | "find all content wasDerivedFrom source X" |

### Webhooks & Events

| Feature | Status | Notes |
|---------|--------|-------|
| Webhook on translation complete | 💡 | Push notification to downstream systems |
| Webhook on deployment recorded | 💡 | Trigger CMS cache invalidation |
| Event stream (SSE) for real-time dashboard updates | 💡 | Live stats without polling |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs implementing any `📋 Planned` item are especially welcome.
To propose a new `💡 Suggested` feature, open a GitHub issue with the label `enhancement`.
