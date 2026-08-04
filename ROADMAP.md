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
| **Non-cooperative page review — fetch + rewrite loader (any URL)** | ✅ | `app/core/page_fetch.py`, `GET /api/v1/pages/render` — headless-browser (Playwright) fetch, harvests/matches/tags translatable text server-side, no SDK tagging or app changes required. Verified live against peripateticware (169 real segments harvested/translated/reviewed) |
| Live-session bridge (browser extension) for pages needing real cookies/session state | ✅ | `frontend/extension/` — Manifest V3, reuses Phase 8's harvest/match engine against a real tab's live DOM instead of an anonymous fetch. See "Live-Session Bridge" below |
| Page-level review notes (not tied to one segment) + editor view for human-drafted proposals | ✅ | `PageNotes.tsx`, `PendingChanges.tsx` — a reviewer's own draft goes through the same human-in-the-loop approval as a redrive, then shows as a dashed-purple highlight until approved individually or in bulk |
| Adopt the SDK in a real target app (peripateticware) instead of the demo fixture | — | Superseded by the fetch+rewrite loader above — peripateticware is now reviewable without any source changes, so cooperative-tagging adoption is no longer the only path |
| **Page history / time-travel — browse, diff, and revert a page's past versions** | ✅ | `app/core/page_history.py`, `PageHistory.tsx` — reconstructs "page as of time T" from existing `TranslationUnitVersion` history + a `PageSnapshot` template, no new snapshot-storage system. `GET /api/v1/pages/render?as_of=`, `/history`, `/diff`; revert via `POST /translations/{id}/versions/{id}/revert` |
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
| Page fetch/harvest/render API tests (against a local static fixture server) | ✅ | `tests/test_pages.py` |
| Page history — timeline/as_of/diff tests, revert tests | ✅ | `tests/test_pages.py`, `tests/test_revert.py` |
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

### Non-Cooperative Page Review (Phase 8) — review any URL, no app changes

The cooperative model (Phase 5) requires a target app to embed the SDK
(`data-tu-id` tags). That's a real adoption wall for pages you don't
control the source of — confirmed live against peripateticware, which
loaded fine in the iframe but showed zero segments because it was never
instrumented.

The fix isn't a classical reverse proxy (Weglot/Crowdin-style) — that
reimplements request-proxying, cookie/session handling, and sub-resource
rewriting the browser already does for free. Instead: `app/core/page_fetch.py`
renders the URL with a headless browser (Playwright, needed since most real
apps — peripateticware included — are client-rendered SPAs), walks the DOM
for translatable text, matches/creates a `TranslationUnit` for each element
keyed by `sha256(url + dom_path + text)` (stored in `source_id`, so
re-fetching the same page reuses history instead of duplicating/
re-translating), tags each with `data-tu-id`, swaps its text to the target
locale, resolves all asset URLs to absolute, injects the review-sdk script
(compiled to a standalone bundle — `frontend/review-sdk/dist/overlay.js`,
since this response never goes through Vite's dev-transform), and serves it
same-origin at `GET /api/v1/pages/render?url=...`. A `PageSnapshot` table
caches fetches so repeat loads are instant; `refresh=true` forces a live
re-fetch. The Review tab's "Any URL" mode just points the existing
`ReviewFrame` iframe at this endpoint instead of an SDK-tagged app's own
URL — no new loader abstraction needed.

Verified live against `localhost:3000` (peripateticware): 169 real segments
harvested, translated, and reviewable through the full segment drawer
(source/target/model/provenance), with zero changes to peripateticware's
own code.

Known limitations, by design: fetches are always anonymous (no login
session) — an app that shows different content to logged-out visitors will
be reviewed as a logged-out visitor sees it; not SSRF-hardened against
private IP ranges, since the point is reviewing your own infrastructure
including localhost; `dom_path`-based matching can drift across a real
redesign, creating a near-duplicate unit rather than updating the old one.

**Next**: a live-session bridge (Phase 10, below) — a browser extension
reusing this same harvest/match engine against a real logged-in tab instead
of an anonymous fetch, for pages that need real session state.

### Page History / Time Travel (Phase 9) — browse, diff, and revert

Motivated by "a git tree for the website content" — browsing what a page
looked like at different points in the project, like the Wayback Machine,
to compare or revert to an earlier version. The key design insight: this
needed almost no new storage. `TranslationUnitVersion` (Phase 2) is already
an append-only, timestamped commit log — one row per change to each
segment. What was missing was the "checkout a whole tree as of commit X"
operation, which `app/core/page_history.py` implements as a reconstruction
*query*, not a new snapshot system: the latest `PageSnapshot` template
(Phase 8) at or before a given time, with each `data-tu-id`'s text
substituted for whichever `TranslationUnitVersion` was current at that
moment (a leaf-only-elements regex swap — safe because Phase 8's harvest
guarantees no nested elements inside a tagged node).

- `GET /api/v1/pages/render?as_of=<timestamp>` — point-in-time
  reconstruction; omitted `as_of` falls back to Phase 8's normal behavior.
- `GET /api/v1/pages/history` — the distinct timestamps at which something
  on the page's harvested units changed (the "commit list").
- `GET /api/v1/pages/diff?from_ts=&to_ts=` — which segments differ between
  two points, with before/after text.
- `POST /api/v1/translations/{id}/versions/{id}/revert` — restores an old
  version's text as a *new* version (`source_event="revert"`), reusing
  `save_translation_unit`'s existing diff-on-target_text write path so the
  `wasRevisionOf` PROV chain (built from version history) picks it up with
  no special-casing — never rewrites history, consistent with this
  system's append-only provenance model throughout.
- Review Shell: a "History" panel (`PageHistory.tsx`, fetch mode only) with
  a timeline dropdown to load a past version and a from/to diff view;
  `VersionHistory.tsx` gets a "Revert to this version" button per row.

Known limitation: structural drift isn't auto-caught — reconstruction can
only substitute *text* into the *most recent* template at or before the
requested time, so a redesign that changed the page's actual structure
between two fetches isn't reflected in an as_of render from before that
redesign. Re-fetching (Phase 8's "Force refresh") captures a fresh
template; periodic/scheduled re-crawling to catch drift automatically is
explicitly out of scope, a deliberate deferral rather than an oversight.

### Live-Session Bridge (Phase 10) — real tabs, page-level notes, human drafting

Phase 8's fetch is always anonymous — no cookies, no login session — so a
page that shows different content to a logged-out visitor gets reviewed as
a logged-out visitor sees it. This phase reuses Phase 8's harvest/match
engine against a REAL tab's live DOM instead: cookies, session, sub-resource
loading, and client-side routing all work for free because it's the
browser's own session. Not a classical reverse proxy, same rationale as
Phase 8.

- **Shared harvest logic, not duplicated** — the harvest/rewrite JS that
  used to live as Python string literals inside `page_fetch.py` was
  extracted to `frontend/review-sdk/harvest.ts`, compiled to
  `dist/harvest.js`. `page_fetch.py` reads the compiled JS from disk;
  Playwright's `page.evaluate` and the extension's content script both call
  the exact same code.
- **`POST /api/v1/pages/harvest`** — the matching/creation step
  (`match_or_create_units`) extracted as its own endpoint: the extension's
  content script walks the DOM itself (no headless browser involved — the
  real tab already is the browser), posts `{idx, domPath, text}` items, and
  gets back `{tuId, sourceText, targetText, latestScore}` per item.
- **`overlay.ts` gets a pluggable transport** — a `ReviewTransport`
  interface (`send`/`onMessage`) replaces the hardcoded `postMessage` calls;
  the default `PostMessageTransport` keeps Phase 5/8/9's iframe hosting
  unchanged, and the extension supplies a `chrome.runtime`-based one
  instead. The box-drawing/click logic itself doesn't change either way.
- **The extension** (`frontend/extension/`, Manifest V3): `background.ts`
  relays messages between the reviewed tab and the Review Shell's tab by
  `chrome.tabs` id; `harvest-content-script.ts` runs the shared harvest
  logic and tags matched elements with `data-tu-id` **without swapping
  text** (unlike Phase 8/9 — swapping a live page's real text while someone
  might be using the real site would be surprising and hard to undo cleanly;
  overlay boxes + score coloring are enough, and the localized text can
  already be seen via Phase 8/9's rendered view of the same URL);
  `bridge-content-script.ts` relays `chrome.runtime` messages into
  `window.postMessage` on the Review Shell's own page, so `ReviewPage.tsx`
  needs no changes to receive `tu:selected` from a different source;
  `popup.html`/`popup.ts` is the toolbar popup (target-language input, a
  "start reviewing this tab" toggle, and a mini notes panel).
- **Page-level notes** — motivated by a reviewer doing a final revision
  pass who needs to record something that doesn't map to one segment ("use
  formal register throughout this page"). `ReviewNote` became polymorphic
  (`unit_id` now optional; new optional `page_url`/`target_language`) rather
  than a new table. `GET/POST /api/v1/pages/notes`,
  `PUT /api/v1/pages/notes/{id}/resolve`; `PageNotes.tsx` is the same
  list+add+resolve pattern `NotesThread.tsx` already used, surfaced in both
  the Review Shell's fetch-mode sidebar and the extension's popup.
- **Live drafting + editor view** — a reviewer can type their own draft for
  a segment right in `SegmentDrawer`; "Propose translation" calls
  `POST /api/v1/redrive/propose`, which creates a single-item ad-hoc
  `RedriveRun` (`scoring_provider="human"`, `redrive_provider="human"`) with
  one `PENDING_APPROVAL` item — the exact same human-in-the-loop mechanism
  Phase 3's scorer-triggered redrives use, so approval reuses
  `approve_item`/`reject_item` unchanged. `GET /api/v1/pages/pending` lists
  every unapproved proposal on a page; `POST /api/v1/redrive/items/bulk-
  approve` approves several at once. `PendingChanges.tsx` is the editor
  view: source/current/proposed text per pending item, with individual and
  "Approve all" actions; a segment with a pending proposal gets a distinct
  dashed-purple overlay box instead of score-coloring, both driven by a new
  `has_pending_proposal` field on `GET /translations/batch`.

Verified live end-to-end (propose → dashed-purple highlight appears → shows
in the pending panel → approve → text updates on the page → History/Diff
reflect it correctly), which surfaced two real bugs, both fixed: `pages.py`'s
`as_of`/`diff` endpoints 500'd on a tz-aware timestamp (e.g. the frontend's
own `new Date().toISOString()`) because every stored timestamp is a naive
`datetime.utcnow()` — fixed by normalizing at the API boundary; and
`save_translation_unit` stamped every version's `created_at` from
`unit.translated_at` (which only ever reflects unit-*creation* time, never
updated by a redrive/approve), so an approved edit's new version got the
exact same timestamp as the original and lost a tie-break in `as_of`/diff
reconstruction — fixed by only trusting `translated_at` when a caller
deliberately advances it past the prior version. 3 regression tests added
via the real propose→approve path; full suite 77/77 passing.

The extension itself can't be exercised through this project's usual
browser-automation verification (`chrome://extensions`' "Load unpacked" flow
is a native file picker, opaque to CDP) — the harvest/overlay/bridge/notes/
propose flow it drives was verified through the fetch-mode UI that shares
the same code paths; loading the extension against a real logged-in site is
a manual step for whoever installs it.

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
