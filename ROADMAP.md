# Roadmap

Status legend: ✅ Built · 🔧 Partial · 📋 Planned · 💡 Suggested

---

## v1.0 — Current Build

### Core Provenance Engine

| Feature | Status | Notes |
|---------|--------|-------|
| W3C PROV-DM data model (Entity / Activity / Agent) | ✅ | `app/models/schemas.py` |
| All seven PROV relations (wasGeneratedBy, wasDerivedFrom, wasAttributedTo, used, wasAssociatedWith, wasInformedBy, wasRevisionOf) | ✅ | `app/core/prov_builder.py` |
| PROV-JSON serialisation (W3C Submission) | ✅ | `GET /api/v1/provenance/{id}/prov-json` |
| PROV-N human-readable notation | ✅ | `GET /api/v1/provenance/{id}/prov-n` |
| Provenance bundle per translation unit with XLIFF cross-reference (`xliff_document_id`) | ✅ | `ProvenanceRecord.xliff_document_id` |
| Lineage graph output (nodes + edges) for visualisation | ✅ | `GET /api/v1/provenance/{id}/lineage` |
| Review workflow: human post-edit creates new PROV Activity + Agent | ✅ | `PUT /api/v1/translations/{id}/review` |
| Deployment provenance (Publication activity + DeployedContent entity) | ✅ | `POST /api/v1/translations/{id}/deploy` |
| Version history per unit, with `wasRevisionOf` chain across versions | ✅ | `TranslationUnitVersion`, `GET /api/v1/translations/{id}/versions` |
| QualityAssessment activity (scorer agent, `wasInformedBy` link from a redrive back to the assessment that triggered it) | ✅ | `app/core/prov_builder.py` |
| Same PROV pattern extended to image assets (`SourceImage`/`TranslatedImage`) | ✅ | `build_image_provenance_record()` |

### XLIFF 2.0

| Feature | Status | Notes |
|---------|--------|-------|
| XLIFF 2.0 document generation (ISO 21720:2017) | ✅ | `app/xliff/xliff_service.py` |
| Full W3C PROV bundle embedded in every `<unit>` | ✅ | All entities, activities, agents, relations as `<note>` elements |
| Per-version history embedded as human-readable notes | ✅ | `provx:version` notes alongside the formal `wasRevisionOf` relations |
| `prov:bundleId` cross-reference on `<xliff>` and `<unit>` | ✅ | Links back to `/provenance/{id}/prov-json` |
| BCP-47 language tags on `<source>` and `<target>` | ✅ | `dc:language` attribute |
| Dublin Core metadata (created, date, language) | ✅ | `dc:created`, `dc:date` |
| Custom `provx:` namespace (confidence, quality, deployment) | ✅ | `urn:ai-provenance:xliff-ext:1.0` |
| XLIFF state mapping (initial / translated / reviewed / final) | ✅ | `_xliff_state()` |
| XLIFF document parser (reconstruct PROV from `<note>` elements) | ✅ | `parse_xliff_document()` |
| Single-unit XLIFF export | ✅ | `GET /api/v1/xliff/{id}` |
| Project-level XLIFF export (all units in one document) | ✅ | `GET /api/v1/xliff/project/{id}` |
| **XLIFF import** — ingest external XLIFF, synthesize provenance if none embedded | ✅ | `POST /api/v1/xliff/import`, `app/xliff/xliff_import.py` |
| **Ingest ledger** — every import/export logged (direction, source system, unit count) | ✅ | `GET /api/v1/xliff/ingest-log` |
| XLIFF 2.0 `<matches>` module (translation memory hits) | 📋 | Leverage existing TM for provenance |
| XLIFF `<glossary>` module support | 📋 | Terminology tracking |
| XLIFF validation against official NVDL schema | 📋 | Strict conformance check |

### Threshold-Quality Redrive

| Feature | Status | Notes |
|---------|--------|-------|
| Deterministic free quality checks (untranslated/garbage/placeholder/script/HTML-tag/number-mismatch/truncation) | ✅ | `app/core/scoring/deterministic.py`, ported from peripateticware's `qa_review_llamacpp.py` |
| MQM-style scoring via Claude-as-judge | ✅ | `app/core/scoring/claude_scorer.py` |
| Local Ollama QE scorer | ✅ | `app/core/scoring/ollama_scorer.py` |
| Pluggable scorer selection | ✅ | `SCORING_PROVIDER=claude\|ollama`, `app/core/scoring/factory.py` |
| RedriveEngine — score, threshold, redrive via pluggable translation backend | ✅ | `app/core/redrive/engine.py` |
| Human-in-the-loop — redrives proposed but not applied until approved | ✅ | `require_human_approval`, `POST .../items/{id}/approve\|reject` |
| DB-backed per-provider usage ledger (redrive budget tracking) | ✅ | `app/core/redrive/ledger.py` |
| Redrive run API — create/status/preview/queue | ✅ | `app/api/redrive.py` |
| Scorer-failure resilience (one bad unit can't crash a batch run) | ✅ | `RedriveEngine._score_unit` |
| BLEU / chrF automatic quality estimation | 📋 | Additional signal alongside the LLM-judge scorers |
| Provenance diff — compare two versions of a translation | 📋 | `wasRevisionOf` chain traversal / rendering |

### Image Assets

| Feature | Status | Notes |
|---------|--------|-------|
| Context images (screenshots linked to a text segment) | ✅ | `POST /api/v1/images/{id}/context-link` |
| Translatable image assets with their own provenance chain | ✅ | `ImageTranslationUnit`, reuses the text PROV builder pattern |
| Upload → pending → attach target → completed flow | ✅ | `app/api/images.py` |
| Local filesystem storage | ✅ | `IMAGE_STORAGE_DIR`, Docker volume |
| Overlay text units within an image (OCR/text-in-image extraction) | 📋 | `ImageTranslationUnit.overlay_text_unit_ids` exists; nothing populates it automatically yet |

### Review Environment (In-Context Overlay)

| Feature | Status | Notes |
|---------|--------|-------|
| In-context visual overlay — highlight boxes drawn directly on the rendered target page | ✅ | `frontend/review-sdk/overlay.ts` |
| Cooperative tagging primitive (`data-tu-id`) | ✅ | `reviewTagProps.ts`; `useReviewT.ts` documents the react-i18next binding shape for real-app adoption |
| Score-based highlight coloring | ✅ | Batch-fetched via `GET /api/v1/translations/batch` |
| postMessage protocol between overlay and Review Shell | ✅ | `tu:ready` / `tu:selected` / `tu:preview` / `tu:scrollTo` |
| Segment drawer — source/target, live-preview editing, version history, provenance, notes | ✅ | `frontend/src/components/SegmentDrawer.tsx` |
| Worst-score-first flagged-segment sidebar (accessibility fallback) | ✅ | `PageFlaggedList.tsx` |
| Redrive console — scope/threshold/human-approval UI with dry-run preview | ✅ | `RedriveConsole.tsx` |
| Standalone image review (upload/localize/attach) | ✅ | `ImageReview.tsx` |
| Search UI | ✅ | `SearchPage.tsx` |
| Review notes thread (threaded, resolvable) | ✅ | `app/api/notes.py`, `NotesThread.tsx` |
| Demo target fixture for self-contained verification | ✅ | `frontend/demo-target/` |
| Non-cooperative loader (browser extension / proxy) for pages that block framing or that we don't control | 📋 | `PageLoader` interface designed for this (`ReviewFrame`'s `send`/`onSelect`/`onReady` contract); not built |
| Adopt the SDK in a real target app (peripateticware) instead of the demo fixture | 📋 | Deliberately deferred — see Phase 7 below |
| **Document formats in-context review — text/Markdown** | ✅ | `app/api/documents.py`, `DocumentViewer.tsx`, `DocumentsPage.tsx` — each paragraph/block becomes a `TranslationUnit`, reviewed through the same overlay SDK as any page |
| **Document formats in-context review — PDF/PowerPoint/DOCX** | 📋 | Requested but not yet designed — needs its own investigation into text-layer/coordinate extraction per format and how much of the overlay contract carries over |

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
| Website, Banner Ad, Marketing Campaign, Email, Mobile App, Social Media, Print, API | ✅ | `DeploymentContext` enum |
| Multiple deployment records per translation | ✅ | Each gets its own PROV `Publication` activity |
| Deployment retirement / inactive tracking | ✅ | `DeploymentRecord.is_active`, `retired_at` |

### Search (Haystack)

| Feature | Status | Notes |
|---------|--------|-------|
| Haystack 2.x integration | ✅ | `app/core/haystack_pipeline.py` |
| In-memory document store | ✅ | Default (search index only — translations themselves are in Postgres) |
| Sentence-Transformers embedding (all-MiniLM-L6-v2) | ✅ | Semantic search |
| BM25 keyword search fallback | ✅ | When Haystack unavailable or `semantic=false` |
| Filter by translation method / deployment context / language pair | ✅ | |
| Qdrant persistent vector store | 🔧 | Config present, needs `--profile search` |
| Elasticsearch document store | 🔧 | Config present, needs `--profile full` |

### Persistence

| Feature | Status | Notes |
|---------|--------|-------|
| PostgreSQL backend (asyncpg + SQLAlchemy 2.x) | ✅ | `app/core/db/` — the system of record for everything |
| Database migrations (Alembic) | ✅ | `alembic/versions/0001`–`0007` |
| Docker image runs migrations on startup | ✅ | `Dockerfile` |
| pgvector for embedding storage alongside translations | 📋 | Currently a separate Haystack in-memory index |

### API & Infrastructure

| Feature | Status | Notes |
|---------|--------|-------|
| FastAPI application with async lifespan | ✅ | `app/main.py` |
| CORS middleware | ✅ | Configurable via `CORS_ORIGINS` |
| Environment-based config (`.env`) | ✅ | `app/core/config.py`, `.env.example` |
| Dockerfile | ✅ | Python 3.12-slim, model pre-download, runs Alembic before serving |
| Docker Compose (dev / search / full profiles) | ✅ | `docker-compose.yml` — host ports offset (8001/5433) to coexist with another project's stack on the same ports |
| Makefile with common tasks | ✅ | `make run`, `make test`, `make migrate`, `make frontend-dev`, `make demo-dev` |
| pyproject.toml (packaging + pytest + ruff) | ✅ | |
| `.gitignore` | ✅ | Python, venv, node_modules, secrets, ML models, runtime image storage |
| MIT License | ✅ | |
| CONTRIBUTING.md | ✅ | |

### Review Shell (Frontend)

Replaces the old single-file `frontend/index.html` dashboard — see "Review
Environment" above for the full breakdown. Vite + React + TypeScript.

### Tests

| Feature | Status | Notes |
|---------|--------|-------|
| Unit tests — models, XLIFF generation + round-trip parse, PROV builder | ✅ | `tests/test_provenance.py` |
| API integration tests — translations, provenance, XLIFF export/import, search | ✅ | `tests/test_api.py` |
| Redrive engine tests, incl. human-in-the-loop approve/reject | ✅ | `tests/test_redrive.py` |
| Image asset API tests | ✅ | `tests/test_images.py` |
| Document import/segments API tests | ✅ | `tests/test_documents.py` |
| Postgres-backed test fixtures (schema reset per session) | ✅ | `tests/conftest.py` |
| pytest-asyncio, session-scoped event loop | ✅ | `pyproject.toml` |
| Frontend test suite | 📋 | Currently covered by manual browser verification only |

---

## v1.1 — Planned Next

### Provenance Enhancements

| Feature | Status | Notes |
|---------|--------|-------|
| PROV-XML serialisation | 📋 | W3C alternate serialisation for RDF/linked-data tooling |
| PROV-O (OWL ontology) export | 📋 | Semantic web / linked open data interoperability |
| Machine-readable provenance certificate (signed JSON-LD) | 📋 | Cryptographic attestation of AI involvement |
| Bulk provenance export (all units in a project) | 📋 | PROV-JSON archive |

### Quality & Review

| Feature | Status | Notes |
|---------|--------|-------|
| Review assignment queue (route specific units to specific reviewers) | 🔧 | The worst-first redrive queue exists; per-reviewer assignment doesn't |
| OCR-driven overlay text extraction for translatable images | 📋 | See Image Assets above |

### Document Formats In-Context Review (PDF, PowerPoint, DOCX)

Text and Markdown are done (Phase 7a, see "Review Environment" above) —
`POST /api/v1/documents/import` splits an uploaded `.txt`/`.md` file into
paragraph/block segments (each an ordinary `TranslationUnit` tagged with
`{document_id, position}` in its metadata), and `DocumentViewer.tsx` renders
them back as a `data-tu-id`-tagged page served from the Review Shell's own
origin — the existing overlay SDK needs no changes to review it. Markdown
segments render through `marked` + `DOMPurify` before tagging.

PDF/PowerPoint/DOCX (Phase 7b) remain tracked per an explicit request, not
yet designed — needs its own investigation into PDF text-layer/coordinate
extraction, PPTX shape/text-frame mapping, and DOCX paragraph/run mapping,
none of which can reuse the DOM-based overlay the way text/Markdown did.

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
| Non-cooperative review overlay (browser extension / rewriting proxy) | 💡 | For pages we don't control or that block iframing — see Review Environment above |

### AI Act & Regulatory Compliance

| Feature | Status | Notes |
|---------|--------|-------|
| EU AI Act risk classification per translation | 💡 | Flag high-risk use cases by deployment context |
| AI transparency disclosure generator | 💡 | Auto-generate "translated by AI" disclosures for regulated contexts |
| Audit log export (CSV / XLSX) | 💡 | Compliance reporting for legal/procurement — the ingest ledger and redrive run history are a start |
| GDPR data subject export | 💡 | Export all provenance records for a given user |
| Data retention policy enforcement | 💡 | Auto-expire / anonymise old records |

### Analytics & Reporting

| Feature | Status | Notes |
|---------|--------|-------|
| Translation volume dashboard (by language pair, method, context) | 💡 | The current Dashboard tab is totals-only |
| Cost tracking (per-word rates by provider) | 💡 | Connect to billing APIs; the usage ledger tracks characters, not cost |
| Quality trend over time | 💡 | Quality scores are recorded per-version; nothing plots the trend yet |
| Agent performance report (AI vs human confidence/quality) | 💡 | |

### Multi-Tenancy & Auth

| Feature | Status | Notes |
|---------|--------|-------|
| API key authentication | 💡 | `api_key_required`/`api_key` settings exist but are unenforced anywhere |
| OAuth2 / JWT support | 💡 | Enterprise SSO integration |
| Organisation / project namespacing | 💡 | Isolate provenance records per client |
| Role-based access control (RBAC) | 💡 | PM / reviewer / admin roles — review notes/redrive approvals currently take a free-text actor name, not an authenticated identity |

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
| Webhook on redrive run completed / item pending human approval | 💡 | Would pair well with the human-in-the-loop flow |
| Event stream (SSE) for real-time dashboard updates | 💡 | Live stats without polling |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs implementing any `📋 Planned` item are especially welcome.
To propose a new `💡 Suggested` feature, open a GitHub issue with the label `enhancement`.
