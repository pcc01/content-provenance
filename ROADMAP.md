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

### Site I18n & Compliance Audit Toolkit

Distinct in kind from the rest of this table: audits arbitrary THIRD-PARTY
sites (not this system's own translations) for i18n/l10n/compliance
issues — built as a consulting-practice tool (international-expansion
readiness audits, with the report itself doubling as a lead-generation
asset). See "Site I18n & Compliance Audit Toolkit (Phase 11)" and
"Consulting-Grade Checks, Regulatory Data & PDF Report (Phase 12)" below
for the full design.

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-page crawl of a third-party site | ✅ | `app/core/audit/crawler.py` — Playwright-based (renders client-side/SPA content, unlike the raw-HTTP scripts this replaces), reuses Phase 8's `robots.txt` check |
| Mixed-locale detection | ✅ | `app/core/audit/checks/mixed_locale.py` — page-language mismatches, multi-language pages, cross-language internal links, mismatched external YouTube embeds |
| RTL / logical-CSS-properties readiness | ✅ | `app/core/audit/checks/rtl_readiness.py` — physical vs. logical CSS property usage, `:dir()`/`[dir=]` support signal |
| ICU / i18n-tooling detection | ✅ | `app/core/audit/checks/icu_i18n.py` — library signatures (react-intl, i18next, `Intl.*`, ...) and literal leaked ICU MessageFormat syntax in rendered text |
| Privacy-policy review + language-mismatch check | ✅ | `app/core/audit/checks/privacy.py` — finds privacy/legal-labeled links and flags when the linked policy's language doesn't match the linking page's |
| Text expansion / truncation risk | ✅ | `app/core/audit/checks/text_expansion.py` — fixed-width CSS combined with clipped/hidden overflow, a common expansion blocker for longer translated text |
| Font / script coverage | ✅ | `app/core/audit/checks/font_coverage.py` — flags a page targeting Arabic/Hebrew/CJK/Devanagari/Thai with no script-covering font-family declared |
| hreflang / SEO localization | ✅ | `app/core/audit/checks/hreflang.py` — missing hreflang annotations, missing `x-default`, non-reciprocal hreflang links |
| Cookie consent detection | ✅ | `app/core/audit/checks/cookie_consent.py` — known CMP signatures or banner text, checked against which regions actually require affirmative consent |
| Untranslated placeholder leakage | ✅ | `app/core/audit/checks/placeholder_leak.py` — `{{var}}`, `%s`, `{0}`, TODO/Lorem-ipsum surviving into rendered output |
| Locale format assumptions | ✅ | `app/core/audit/checks/locale_format.py` — US-centric form validation (zip/phone/state-dropdown) and hardcoded `$`/date formatting, on non-US-targeted pages |
| Region → regulation mapping with real jurisdiction data | ✅ | `app/core/audit/regions.py` + `app/core/audit/data/jurisdictions/*.json` — ported (data only, not a live dependency) from the user's own privacy-compliance engine built for peripateticware |
| Persisted, reviewable audit runs | ✅ | `SiteAudit`/`SiteAuditPage`/`SiteAuditFinding` tables, `app/api/audit.py` |
| Editor UI + handoff into existing review tooling | ✅ | `AuditPage.tsx`/`AuditReport.tsx` — a finding's "Review this page" button jumps straight into Phase 8's fetch-mode review for that URL |
| Branded PDF report | ✅ | `app/core/audit/report.py` (reportlab) — logo, executive summary, findings by check/severity, legal-disclaimer + consulting CTA closing section |

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
| Site audit tests — 10 checks + PDF export against a local fixture site | ✅ | `tests/test_audit.py` |
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

### Site I18n & Compliance Audit Toolkit (Phase 11)

Distinct in kind from Phases 1–10, which manage translations THIS system
owns end-to-end: this phase audits arbitrary THIRD-PARTY sites from the
outside — crawling for mixed-locale content, checking pages for flexbox/
logical-CSS-property RTL-readiness, detecting ICU/i18n tooling in use, and
reviewing privacy policies. Replaces three standalone Python scripts (each
a requests+BeautifulSoup+langdetect crawler writing its own `.txt` report,
no persistence, no shared crawl, no RTL or ICU checks at all) with a
Postgres-backed, reviewable equivalent — full integration into the app was
the user's explicit choice over keeping them as standalone scripts, along
with latitude to redesign the check implementations rather than port the
scripts' logic as-is.

- **Crawl engine** (`app/core/audit/crawler.py`) — Playwright, not
  requests+BeautifulSoup, so client-rendered SPA content is seen (the exact
  gap Phase 8 already solved once for this system's own review flow). One
  shared browser instance per crawl; reuses Phase 8's `_check_robots_allowed`
  before every fetch (a real upgrade over the scripts, which check nothing).
  A single `page.evaluate()` per page extracts text blocks, links,
  stylesheet/script URLs + bodies (fetched via the same browser context —
  no separate HTTP client), and iframe URLs — no DOM re-serialization
  needed. BFS same-domain(+subdomain), `max_pages` cap (default 40), a
  politeness delay between page loads (the scripts had none).
- **Four pluggable checks** (`app/core/audit/checks/`), each a pure
  function over already-crawled data (no I/O of their own):
  - `mixed_locale.py` — redesigned version of what the scripts did: page-
    language mismatches (detected vs. URL-path-implied locale), pages
    mixing languages, cross-language internal links, mismatched external
    YouTube embeds (`hl` param).
  - `rtl_readiness.py` (new) — counts physical CSS properties
    (`margin-left`, `text-align: left`, `float: right`, ...) against
    logical equivalents (`margin-inline-start`, `text-align: start`, ...)
    across a page's stylesheets; flags heavy physical usage with no
    logical-property or `:dir()`/`[dir=]` support as RTL-risk. A heuristic
    signal, not a compliance certification.
  - `icu_i18n.py` (new) — greps script bodies for i18n library signatures
    (react-intl, i18next, `Intl.*`, ...) and separately greps the page's
    own RENDERED TEXT for literal, unparsed ICU MessageFormat syntax
    (`{count, plural, ...}`) — a real visible bug if it leaks into what a
    visitor actually sees.
  - `privacy.py` — finds privacy/legal-labeled links (extends the scraper
    script's keyword list) and, new, flags when the linked policy's
    language doesn't match the linking page's — reuses `mixed_locale`'s
    detection rather than a separate mechanism.
- **Data model** — `SiteAudit`/`SiteAuditPage`/`SiteAuditFinding` mirror
  `RedriveRun`/`RedriveRunItem`'s parent-run + child-rows pattern, one
  level deeper for the crawled-page inventory. `SiteAuditFinding.detail` is
  a free-form JSON blob (same flexibility `RedriveRunItem.detail` already
  relies on) — new finding types need no schema change.
- **API** (`app/api/audit.py`) — `POST /audit/runs` runs synchronously and
  returns the completed audit, same "await the whole run" convention as
  `redrive.py`'s `POST /runs` rather than adding background-task
  infrastructure; `GET /audit/runs/{id}`, `/pages`, `/findings` (filterable
  by check/severity/page), `/export` (plain-text report, preserving the
  scripts' familiar output format).
- **Frontend** — a new "Audit" tab (`AuditPage.tsx`/`AuditReport.tsx`):
  start a run, browse past runs, findings grouped by check with severity
  coloring. The one deliberate cross-phase tie-in: a finding's "Review this
  page" button hands off directly into Phase 8's existing fetch-mode
  review for that exact URL (`ReviewPage.tsx` gained an
  `initialFetchTarget` prop for this), instead of living in an isolated
  silo.

Verified live in Chrome against a local fixture site seeded with one issue
per check (a mislabeled-locale page, RTL-risk CSS, an i18n-library
reference, a leaked ICU string, and a French privacy policy linked from an
English page): all five expected findings rendered correctly grouped by
check with correct severity coloring, and the "Review this page" handoff
correctly loaded the flagged page into fetch-mode review. 6 new backend
tests (`tests/test_audit.py`) against a local static multi-page fixture
server (same pattern `test_pages.py` already uses), full suite 83/83
passing, both frontend TS projects clean.

**Known limitations, by design**: the crawl runs synchronously within the
request (bounded by `max_pages`, not background-task infrastructure); the
RTL/ICU checks are heuristic signals ("worth a human look"), not
compliance certifications; `langdetect` accuracy on short text blocks is a
carried-forward limitation from the scripts this replaces, not solved here.

### Consulting-Grade Checks, Regulatory Data & PDF Report (Phase 12)

Motivated by the toolkit's actual use case: auditing prospective clients'
sites as part of an international-expansion consulting practice, with the
report doubling as a lead-generation asset. Three additions on top of
Phase 11's four checks.

**Six more checks**, all in `app/core/audit/checks/`: text expansion/
truncation risk (fixed-width CSS + clipped overflow — translated text
commonly runs 20-35% longer than English), font/script coverage (a page
targeting Arabic/Hebrew/CJK/Devanagari/Thai with no script-covering
font-family declared — heuristic by design, no font-file parsing or new
heavy dependency), hreflang/SEO localization (missing annotations, missing
`x-default`, non-reciprocal links), cookie-consent detection (known CMP
signatures or banner text, checked against which regions actually require
affirmative consent), untranslated-placeholder leakage (`{{var}}`, `%s`,
`{0}`, TODO/Lorem-ipsum surviving into rendered output — a broader version
of Phase 11's ICU-syntax-leak check), and locale-format assumptions
(US-centric form validation — 5-digit zip, US-state dropdown, 10-digit
phone pattern — and hardcoded `$`/date formatting, flagged only on pages
targeting a non-US region). The crawler was extended to collect hreflang
link tags and form input/select-option data these checks need.

**Real regulatory data, ported not live-linked**: the user has a full
privacy-compliance engine already built for peripateticware
(`backend/services/privacy_jurisdiction_resolver.py` + a live Postgres
catalog + an AI-discovery pipeline for unmapped countries) — tightly
coupled to that project's own domain (schools/orgs) and requiring its
server to be running. Porting the ENGINE would mean this audit tool's
regulatory findings silently break whenever another project's server is
down, so only the DATA layer was ported: 9 jurisdiction JSON files (GDPR,
CCPA, LGPD, PIPEDA, PDPA-Singapore, Mexico, Argentina, South Africa,
Australia — FERPA/COPPA deliberately excluded as education-specific)
copied into `app/core/audit/data/jurisdictions/`, read directly by
`app/core/audit/regions.py` with zero live dependency on the source
project. `privacy.py`'s findings now cite real jurisdiction names and a
general-business summary per regulation instead of a hardcoded string
list; `cookie_consent.py` checks the ported data's `compliance_checks`
instead of a fixed tuple of framework names.

Two content-accuracy bugs caught while porting, not just technical ones:
the source files' own `requirements`/`warnings` arrays are written for
peripateticware's education/student-data domain (GDPR's top bullet there
is "Obtain explicit parental consent before any data collection") — wrong
framing for a general commercial-site audit, replaced with hand-written
general-business summaries instead of surfacing the ported arrays
verbatim. And `aepd_ar.json` (Argentina) and `pdpa_singapore.json` both
carry `"framework": "pdpa"` in the source data — a real collision — so
lookups were switched to key off `jurisdiction_id` (unique per file)
instead. A third bug, logic not content: `requires_cookie_consent()`
initially matched on ANY `compliance_checks` key overlap, which
incorrectly caught CCPA's `opt_out_mechanism` key too, producing two
findings (a missing GDPR-style cookie banner AND a missing CCPA opt-out
link) for what's really one requirement under the wrong regime — fixed to
check `jurisdiction_id in ("gdpr_eu", "lgpd_brazil")` explicitly, caught
via a direct smoke-test run before it reached a browser.

**Branded PDF report** (`app/core/audit/report.py`, `reportlab` — a new,
pure-Python-installable dependency): the user's "Word in Bits" logo, an
executive summary table (counts by severity), findings grouped by check
with severity coloring, and a closing section with a legal-disclaimer line
(the automated findings aren't legal advice — a real liability/credibility
consideration for a client-facing deliverable) plus a consulting CTA. New
`GET /api/v1/audit/runs/{id}/report.pdf` endpoint; a "Download PDF report"
link sits next to the existing plain-text export in `AuditReport.tsx`.

Verified live: ran a real audit against the user's own site
(thewordinbits.com, 15 pages) through the browser UI end-to-end — real,
substantive findings (a text-expansion-risk CSS pattern repeated across
the WordPress theme's pages, some `langdetect` noise on short nav-label
text blocks — an already-documented limitation, not a new bug) rendered
correctly grouped by check, and the PDF downloaded and opened correctly.
7 tests in `tests/test_audit.py` (one seeded issue per new check, plus a
PDF-endpoint smoke test), full suite 84/84 passing.

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

### pgGraph & Tone/Style/Voice Provenance (Phase 13)

Full evaluation, options considered, and rationale live in
[`docs/graphrag-provenance-proposal.md`](docs/graphrag-provenance-proposal.md)
— summary: graph layer is plain relational tables in the existing
`pgvector/pgvector:pg16` Postgres instance (no Apache AGE, no second
database — AGE was evaluated as compatible and low-risk but not needed for
the fixed-hop retrieval shape this phase requires), retrieval is
Postgres-native hybrid vector + graph (no Neo4j), and the design leans on
[Barry et al. 2025](https://aclanthology.org/2025.genaik-1.6/)'s
fact-grounded-retrieval lesson: retrieve small structured rows, not raw
style-guide prose, both for token cost and for auditability.

| Feature | Status | Notes |
|---------|--------|-------|
| `graph_nodes` / `graph_edges` tables + recursive-CTE traversal helpers | ✅ | Generalizes the existing `provenance_entities/activities/relations` pattern into a queryable graph — `app/core/db/models.py`, `app/core/db/repository.py` |
| `style_guides` / `style_guide_rules` / `glossary_terms` / `translation_exemplars` (pgvector-backed) | ✅ | Structured, retrievable facts — not vector-searchable prose chunks. `supersedes_id` self-reference + `get_style_guide_chain`'s `WITH RECURSIVE` demonstrate the §3b variable-length-hop case |
| Hybrid vector + graph retrieval (`app/core/graph/retrieval.py`) | ✅ | Vector search seeds candidates, graph traversal expands (sibling rules via `style_guide_id`, `preferredOver` glossary alternatives via `graph_edges`). Falls back to locale/keyword filtering when no embedding model is installed (`app/core/graph/embeddings.py`) — retrieval never fails outright |
| Retrieval wired into AI translation backends before the LLM call | ✅ | `app/api/translations.py`'s create endpoint and the redrive engine's redrive step both retrieve context and pass it into `AnthropicTranslationBackend.translate()`'s new `style_context` param before calling Claude |
| `ContextRetrieval` PROV activity + `StyleGuide`/`GlossaryTerm` PROV entities | ✅ | Reconstructed from `graph_edges` on every provenance rebuild (not passed as a param) so it survives review/deploy/revert rebuilds the same way version history does — `app/core/prov_builder.py` §4d |
| `StyleAdherenceScorer` (tone / voice / terminology) | ✅ | MQM-style, mirrors `ClaudeQualityScorer` — `app/core/scoring/style_scorer.py` + `style_base.py`/`style_factory.py`. Also judges source-language drafts (no translation pair needed) for §9b.5 |
| `style_adherence_scores` table + style score as a second redrive threshold | ✅ | Mirrors `QualityScoreRow`; `RedriveRun.style_threshold` is an independent axis — a unit redrives if EITHER quality or style falls below its threshold — `app/core/redrive/engine.py` |
| `provx:styleAdherence` PROV activity + human-readable style/glossary brief on export | ✅ | The retrieved rule/term facts already flow through the generic `prov:Entity` notes; `_style_brief_lines()` additionally consolidates them into one plain-English `provx:styleBrief` note so vendor-routed (not just AI-routed) work gets the same grounding — `app/xliff/xliff_service.py` |
| TMX import (`app/tm/tmx_import.py`, `app/api/tm.py`) | ✅ | Distinct from XLIFF import — seeds `translation_exemplars` from legacy vendor translation memory (`<tu>`/`<tuv>`), tags `ProvenanceAgent.organization` with the vendor via a `vendor:{source_system}` agent |
| Source-language voice check (`POST /api/v1/style/check-source`) | ✅ | Reuses `StyleAdherenceScorer` locale-parameterized, run source-side before translation |
| Style guide/rule/glossary CRUD + retrieval-preview API | ✅ | `app/api/style.py` — `GET .../retrieve-preview` exposes retrieval read-only for admin verification |
| Style Guides admin page (`StyleGuidesPage.tsx`) + hard-fail-aware `QualityBadge` | ✅ | Built in the Review Shell segmentation pass below, not this one — see "Review Shell Segmentation (Content Creation / Quality Review / Audit)" |

Built in dependency order: schema (migrations `0014`-`0018`) → graph
write-path + query helpers → hybrid retrieval → `ContextRetrieval`
provenance → `StyleAdherenceScorer` + redrive-threshold wiring → TMX
import, XLIFF brief, source-side check → API routers. 24 new tests
(`test_graph.py`, `test_style_scoring.py`, `test_tmx_import.py`,
`test_style_api.py`), full suite 117/117 passing — verified both against
`Base.metadata.create_all` (the dev/test path) and against the real
`alembic upgrade head`/`downgrade -1` migration chain run from a blank
schema.

### Vendor Scorecard & Cross-Document Consistency (Phase 14)

Fast-follow on Phase 13 — both features read Phase 13's data (vendor-
tagged scores, populated glossary/style edges) rather than needing new
ingestion of their own, so they're sequenced after it rather than inside
it. See `docs/graphrag-provenance-proposal.md` §9b for the product
scenario (a PMM managing localization vendors) that surfaced these.

| Feature | Status | Notes |
|---------|--------|-------|
| Vendor/agent scorecard (latest quality + style scores, `GROUP BY` `ProvenanceAgent.organization`) | ✅ | `GET /api/v1/vendors/scorecard` — the artifact a PM actually uses in a vendor renegotiation, not per-segment QA. Ranked best-first; averages use each unit's LATEST score only, not its whole scoring history — `app/core/db/repository.py`'s `get_vendor_scorecard` (Postgres `DISTINCT ON`, one query) |
| Branded scorecard PDF export | ✅ | `GET /api/v1/vendors/scorecard/report.pdf` — reuses the `app/core/audit/report.py` (reportlab) pattern → `app/core/vendors/report.py` |
| `term_drift` / `term_inconsistency` / `tone_spread` consistency checks | ✅ | **Not** wired into `app/core/audit/`'s `SiteAuditCheck` framework as originally sketched — that subsystem audits crawled THIRD-PARTY site HTML (a different data domain), so this got its own module, `app/core/consistency/checker.py`, operating on this system's own `TranslationUnit`s instead |
| Sub-quadratic consistency comparison | ✅ | One graph lookup per unit clusters units by shared `GlossaryTerm`/`StyleGuideRule` edges (O(n)); comparison happens only within each cluster (O(k·n) total) — the technique from Barry et al. 2025 (§7 of the proposal doc), never an O(n²) pairwise scan across `scope` |
| `GET /api/v1/consistency/check` | ✅ | Computed on demand over a `scope` (unit_ids / target_language / source_language / project_id) — same "no persisted run" convention as `GET /redrive/preview`, not a new `SiteAudit`-style run table |
| `VendorScorecardPage.tsx` + `ConsistencyPage.tsx` | ✅ | Built in the Review Shell segmentation pass below — see "Review Shell Segmentation" |

10 new tests (`test_vendors.py`, `test_consistency.py`), full suite
127/127 passing.

### MQM / COMET / METEOR Quality Standards (Phase 15)

Full research, source citations, and the primary-source MQM taxonomy data
live in
[`docs/quality-evaluation-research.md`](docs/quality-evaluation-research.md)
— formalizes this project's ad-hoc "MQM-style" scoring against the real
MQM standard, and adds two non-LLM automatic MT-quality metrics (COMET-Kiwi,
METEOR) as a third, independent scoring axis. Human-perceived quality
(tone/voice — MQM) and MT/translation quality (COMET/METEOR) were
evaluated as two distinct standards per the user's request, alongside a
review of Alon Lavie's 2021-present publication record (METEOR's
co-creator, COMET's research lead).

| Feature | Status | Notes |
|---------|--------|-------|
| 44-item official MQM-Core error taxonomy (7 dimensions) | ✅ | `app/core/scoring/mqm_types.py` — sourced directly from the MQM Council's own `themqm.org/resources/` workbooks (mnemonic Error Type IDs, not invented), CC-licensed |
| Typed `error_type` + `neutral` severity on `ScoreError` | ✅ | `ClaudeQualityScorer` now returns per-error MQM mnemonic + severity (`app/core/scoring/claude_scorer.py`) instead of a single undifferentiated count — the concrete fix for the "one blended severity bucket" gap the research identified |
| `hard_fail` — MQM's "any critical error ⇒ automatic Fail" rule | ✅ | Decoupled from the numeric score (`QualityScore.hard_fail`); `RedriveEngine` treats it as an independent redrive trigger alongside the numeric threshold — a unit scoring 75/100 with one critical error redrives regardless |
| Scoring weights (25/10/3 for critical/major/minor) | ✅ unchanged | Deliberately NOT changed to MQM's literal 25/5/1 defaults — would have silently shifted every existing redrive threshold's behavior; only the taxonomy/hard-fail/neutral additions were in scope |
| `automatic_metric_scores` table — third scoring axis | ✅ | Mirrors `style_adherence_scores`'s "independent, never blended" pattern; a COMET/METEOR number and a Claude MQM-style number answer different questions even when they render the same |
| METEOR scorer + redrive regression-check | ✅ | `app/core/scoring/automatic/meteor.py` (pure NLTK, no GPU) — every redrive automatically records a METEOR score comparing the new candidate against the version it replaced, informational only, never blocks a redrive |
| COMET-Kiwi (reference-free QE) scorer | ✅ code / 📋 not installed | `app/core/scoring/automatic/comet_kiwi.py` — lazy-imports `unbabel-comet` (not installed by default, see requirements.txt) and the gated `wmt22-cometkiwi-da` checkpoint (CC-BY-NC-SA-4.0, free HF login + license click-through, no fee). Adopted under the project's non-commercial/open-source framing — an explicit decision by the project owner, not assumed |
| `POST /api/v1/quality/comet-score` (batch/offline) | ✅ | Deliberately not on any live-request or redrive path — CPU inference on a transformer-scale model doesn't fit a live-latency budget; admin/QA-sampling use only |
| `POST /api/v1/quality/meteor-compare`, `GET /api/v1/quality/{unit_id}/automatic` | ✅ | Ad-hoc comparison and score-history endpoints |

**Bug found and fixed along the way:** `QualityScore`/`StyleAdherenceScore`/
`AutomaticMetricScore`'s "latest score for this unit" queries
(`get_latest_quality_score`, the vendor scorecard's `DISTINCT ON`, ...)
had a latent tie-breaking bug — two scores landing in the same clock tick
(a real scenario: rapid re-scoring during a batch redrive) made "which one
is latest" ambiguous, and Postgres doesn't guarantee which tied row
`DISTINCT ON`/`LIMIT 1` returns. Caught by an intermittent test failure
while validating this phase, not by design. Fixed with a shared
`_strictly_after_latest` helper (`app/core/db/repository.py`) that nudges
a colliding timestamp forward by 1 microsecond before insert — same
reasoning `save_translation_unit` already applies to `TranslationUnitVersion.
created_at`, now applied consistently across all three scores-over-time
tables.

**Code-complete but not live-tested:** COMET-Kiwi's actual model inference
(no multi-GB download attempted in the build/CI environment) — matches
this codebase's existing convention of never exercising `ClaudeQualityScorer`'s
real API call in tests either. Its import-guard/graceful-degradation
behavior IS tested (`test_automatic_metrics.py`).

16 new tests (`test_mqm.py`, `test_automatic_metrics.py`), full suite
143/143 passing (re-run repeatedly to confirm the timestamp-tie-break fix
above holds — it was intermittent before the fix, not deterministic).
`QualityBadge`'s `hard_fail` marker was added in the Review Shell
segmentation pass below; MQM per-error dimension breakdown and inline
automatic-metric (METEOR/COMET) display in the segment drawer are still
not surfaced anywhere in the UI — narrower than the Phase 13/14 gap was,
but still open.

### Review Shell Segmentation (Content Creation / Quality Review / Audit)

The frontend gap called out in Phases 13-15 above — built as one pass
rather than three, since the new pages share a navigation restructure.
The old flat 8-tab bar (Review/Live/Redrive/Images/Documents/Audit/Search/
Dashboard) is now three top-level segments, each matching an actual phase
of the work rather than an arbitrary regroup:

- **Content Creation** — Create, Style Guides, Import, Documents. Where
  content starts its life: define brand voice (Style Guides) before
  anything else has something to check against, bring in legacy vendor
  content (Import — TMX and, for the first time, a UI for the
  previously API-only XLIFF import), then write/check/submit new copy
  (Create — source-side voice check + retrieval preview + translate, all
  three of which had zero UI before this pass).
- **Quality Review** — Review, Live, Redrive (now with a style-threshold
  axis and a style guide selector), Images, Vendor Scorecard, Consistency,
  Search, Dashboard.
- **Audit** — unchanged; a genuinely separate concern (third-party site
  compliance), not folded into Quality Review.

| Feature | Status | Notes |
|---------|--------|-------|
| Segmented `App.tsx` (3 top-level segments, per-segment sub-nav) | ✅ | Replaces the flat tab bar; same inline-style visual language as every existing page, no new dependency |
| `CreateContentPage.tsx` | ✅ | Source-side voice check, retrieval preview, and translation submission — none of the three had a UI entry point before (submitting a translation was API-only even in Phase 1) |
| `StyleGuidesPage.tsx` | ✅ | Guide/rule/glossary CRUD |
| `ImportPage.tsx` | ✅ | TMX (Phase 13) and XLIFF (Phase 1, never had a UI) side by side |
| `VendorScorecardPage.tsx`, `ConsistencyPage.tsx` | ✅ | Ranked table + PDF link; findings list |
| `RedriveConsole.tsx` style-threshold controls | ✅ | Style guide selector + threshold slider, wired into `previewRedrive`/`createRedriveRun` |
| `QualityBadge` `hard_fail` marker | ✅ | Optional/additive prop — existing call sites unaffected |
| MQM per-error dimension breakdown, inline automatic-metric display | 📋 | Still not surfaced — see above |

**Bug found and fixed during live smoke-testing, not by design:**
`new URLSearchParams({key: undefined})` does not drop the key — it calls
`String(undefined)`, producing the literal query string `key=undefined`,
which FastAPI then treats as a real (never-matching) filter value instead
of "omit this filter." Every "blank = show all" filter field across the
new pages was silently broken by this (caught live on the Consistency
page: a blank target-language field returned zero results instead of
everything) — and so was one pre-existing case, `previewRedrive`, that
predates this pass. Fixed with a `cleanParams()` helper
(`frontend/src/api/client.ts`) applied at every affected call site, not
just the newly-discovered one; re-verified live afterward (101 units
checked, 12 real findings, on the same page that returned zero before the
fix).

Verified live end-to-end (not just `tsc -b`/`vite build`, which both pass
clean): Content Creation's check-source/retrieve-preview/translate flow,
Style Guides' guide-select-and-load, Import's form rendering, Vendor
Scorecard's ranked live data, Consistency's findings (after the fix
above), and the Redrive Console's new style controls — all against the
real backend, not mocked.

### Multi-Provider Translate / Evaluate / Retranslate, incl. Tower+ (Phase 16)

Prior phases hard-wired one translation provider (`TRANSLATION_PROVIDER`)
and one evaluation provider (`SCORING_PROVIDER`) at process-start via env
vars. This phase makes every provider selectable **per request, surfaced in
the UI** — not a restart-to-change setting — and adds six new providers:
OpenAI, Google Gemini, Microsoft Translator, LMStudio, vLLM, and Tower/
Tower+ (via the existing Ollama integration, upgraded). Research backing
the Tower+ decisions lives in
[`docs/quality-evaluation-research.md` §10](docs/quality-evaluation-research.md).

| Feature | Status | Notes |
|---------|--------|-------|
| `OpenAITranslationBackend`, `GeminiTranslationBackend`, `MSTranslatorTranslationBackend`, `OllamaTranslationBackend`, `LMStudioTranslationBackend`, `VLLMTranslationBackend` | ✅ | `app/core/translation_backends.py` — 10 providers total now (`mock`, `anthropic`, `openai`, `gemini`, `deepl`, `google`, `mstranslator`, `ollama`, `lmstudio`, `vllm`) |
| `OpenAICompatibleScorer`, `GeminiQualityScorer` | ✅ | `app/core/scoring/openai_compatible_scorer.py`, `gemini_scorer.py` — 6 scoring providers now (`claude`, `ollama`, `gemini`, `openai`, `lmstudio`, `vllm`); `openai`/`lmstudio`/`vllm` share one `OpenAICompatibleScorer` since they speak the same REST API shape |
| Shared MQM prompt/parsing contract | ✅ | `app/core/scoring/mqm_prompt.py` — extracted out of `claude_scorer.py` so Claude/OpenAI/Gemini/LMStudio/vLLM all score against the exact same rubric and JSON contract instead of near-duplicate prompts drifting apart |
| `OpenAICompatibleClient`, `GeminiClient`, `MSTranslatorClient` | ✅ | `app/core/llm_clients.py` — thin raw-`httpx` REST clients, deliberately no new SDK dependencies (matches this codebase's existing `ollama_scorer.py` convention) |
| `TranslateRequest.provider` | ✅ | Per-translation override; `None` = `settings.translation_provider` |
| `RedriveRunRequest.scoring_provider` / `.redrive_provider` | ✅ | Independent axes — evaluate with one model, retranslate with another (e.g. Claude judges, a local model redrives) |
| `POST /api/v1/quality/evaluate` | ✅ | New standalone endpoint — score one unit with a chosen provider on demand, independent of a redrive run; the first-class "evaluate" action the UI needed |
| `CreateContentPage.tsx` "Translate with" dropdown | ✅ | All 10 translate providers, NMT-only ones (Google Translate, MS Translator) labeled as such |
| `RedriveConsole.tsx` "Evaluate with" / "Retranslate with" dropdowns + standalone per-unit evaluate panel | ✅ | Two independent dropdowns (not one) so evaluate/retranslate models can differ; the standalone panel calls `POST /quality/evaluate` directly |

**Tower / Tower+ research (§10), and what was adopted:**
- Confirmed this project's Ollama scorer already was a port of a
  TowerInstruct-via-Ollama approach from peripateticware — the task's
  starting premise, verified from the code's own comments and default model
  string.
- Found a real, independent bug while tracing the prompt template: the
  Ollama scorer (and, before this phase, no Ollama translation backend
  existed at all) used `/api/generate` with hand-rolled Mistral/Llama-2-style
  `[INST]...[/INST]` tags, but TowerInstruct is documented to expect ChatML,
  and Tower+'s three sizes span two unrelated base-model families (Gemma 2,
  Qwen 2.5) with no shared template to hand-roll correctly at all. Fixed by
  switching to Ollama's `/api/chat` endpoint everywhere (`ollama_scorer.py`
  and the new `OllamaTranslationBackend`), which applies whichever chat
  template is embedded in the loaded GGUF instead of guessing.
- Adopted `Tower-Plus-9B` (CC-BY-NC-SA-4.0, 5.76GB Q4_K_M, confirmed GGUF at
  `mradermacher/Tower-Plus-9B-GGUF`) as the new default for **both**
  `ollama_translation_model` and `ollama_qe_model`, replacing
  `TowerInstruct-7B-v0.1` — a real, if self-reported, competitive WMT24++
  translation track record and a lighter footprint than this project's
  already-adopted COMET-Kiwi checkpoint.
- Deliberately did **not** upgrade Tower's evaluation output from coarse
  pass/fail (`ScoreResult(score=40 or 100, ...)`) to typed MQM errors —
  §10.2 found Tower's training data mixes MQM-style and DA-style evaluation
  examples with no confirmed output schema, so parsing structure out of its
  free text would build on an unconfirmed contract. Tower's evaluation mode
  is positioned as a free/local *fallback for the Claude scorer's role*, not
  a peer of it or of COMET-Kiwi (different category of signal — see §10.5).
- Deliberately did **not** add `Tower-Plus-72B` — 47.4GB of 4-bit weights
  alone is incompatible with this project's "no GPU infra assumed" posture,
  same reasoning Phase 15 already applied to COMET-Kiwi's largest variants.

**Scope deliberately cut, stated plainly:** style/tone/voice scoring
(`app/core/scoring/style_factory.py`) remains Claude-only — multi-provider
support was scoped to the main quality/MQM scorer and translation backends
only, not extended to style scoring in this pass.

**Code-complete but not live-tested against real external endpoints:**
OpenAI, Gemini, MS Translator, LMStudio, and vLLM all require credentials or
a locally running server this environment doesn't have — same "code
complete, not live-tested" honesty convention as Phase 15's COMET-Kiwi.
Every provider's *graceful-degradation* path (unknown provider, missing
credentials) IS tested and passing; `MockTranslationBackend`'s round trip
and the deterministic-floor short-circuit are the only paths exercised
end-to-end without a real API key.

17 new tests (`test_multiprovider.py`) — registry completeness for both
factories, "explicit provider always builds fresh" for both, credential
graceful-degradation for anthropic/deepl/openai/gemini/mstranslator, and the
new `/quality/evaluate` endpoint's 200/404/400 paths. Full suite 160/160
passing (143 prior + 17 new). Frontend verified via `tsc -b --force` and
`npm run build`, both clean; not yet re-verified live in the browser the way
the Phase 13-15 segmentation pass was (no live API keys/local model servers
available to drive an actual translate-with-OpenAI or evaluate-with-Gemini
click-through in this environment).

### Closing the Backend-UI Gap (Phase 17)

A systematic audit — every backend route cross-referenced against every
`api.*` call actually made from the frontend — turned up ten working
endpoints with zero UI: some had never had a consumer built, one
(`GET /redrive/queue`) was explicitly *described* as "the review UI's
worklist" in its own docstring and the README without ever actually being
wired to one. This phase closes all ten.

| Feature | Status | Notes |
|---------|--------|-------|
| XLIFF export (download + inline preview) | ✅ | `ProvenancePanel`'s new "Export this unit" section — download links for XLIFF/PROV-JSON/PROV-N plus a lazy-loaded `<details>` preview of the raw XLIFF text. The system's headline deliverable (XLIFF with embedded PROV) had no download button anywhere before this |
| Deployment recording + history | ✅ | `SegmentDrawer`'s new "Record a deployment" form (write) + `ProvenancePanel`'s deployments list (read) — confirmed live: recording a deployment rebuilds the PROV record's summary sentence in real time |
| Mark as reviewed | ✅ | `SegmentDrawer`'s new "Mark as reviewed" button — confirmed live: status flips to "reviewed," a `reviewed_at` timestamp appears, and a `Person` agent joins the PROV record's Agents list |
| Lineage graph + PROV-JSON/PROV-N | ✅ | `ProvenancePanel` — node/edge counts with an expandable edge list; JSON/N remain download-only (raw serialization formats, not meant to render inline) |
| Image context-linking | ✅ | New `ContextImages.tsx` — upload + link a screenshot to a text segment; `ImageReview.tsx` still only handles the standalone `kind="translatable"` path, this is the other half. Backend chain (upload → link → list) verified directly via curl |
| Automatic metric (COMET/METEOR) history | ✅ | New `MetricsPanel.tsx`, a 5th SegmentDrawer tab — the only place these scores were ever visible to a reviewer, as distinct from the MQM judge score on `QualityBadge` |
| Redrive worklist | ✅ | `RedriveConsole`'s new "Worklist" section — worst-first table with a per-row "Evaluate ↓" action that hands the unit id to the existing standalone-evaluate panel below it |
| Ad-hoc METEOR compare | ✅ | `RedriveConsole`'s new "Compare METEOR" tool |
| Style guide version chain | ✅ | `StyleGuidesPage` shows a guide's `supersedes_id` history inline when it has one |
| Audit crawled-page inventory | ✅ | `AuditReport`'s new collapsible "Pages crawled" table (URL/status/html-lang/expected-locale/detected-language) |
| Search indexed-document count | ✅ | The `/search/` response already returned `indexed_documents`/`search_type`; the frontend type just dropped them — no new endpoint needed |

**Bug found and fixed via live testing, not code review:** `getStyleGuideChain`
walks `supersedes_id` *backward* from whichever guide you select — so the
array itself is newest-first. The first version rendered it in that order
under an "(oldest → newest)" label, which put v2.0 before v1.0 while
claiming the opposite. Caught by actually clicking through a real
multi-version guide in the browser, not by reading the code; fixed by
reversing the array before rendering rather than relabeling, since "oldest
→ newest" reads better than the alternative.

**Verified live end-to-end**, not just `tsc -b --force`/`npm run build`
(both clean): opened a real segment in the Review tab and, in order,
recorded a deployment, marked it reviewed, confirmed both changes
propagated into the rebuilt PROV summary/Agents/Activities, expanded the
lineage graph, previewed the raw XLIFF inline, loaded the Redrive
Console's worklist and used its "Evaluate ↓" handoff, ran the METEOR
compare tool (70.1, matching a direct `curl` check of the same endpoint),
walked a real style guide's version chain (where the ordering bug above
was caught), and expanded a real audit run's crawled-pages table. Context
image upload+link was verified via a direct `curl` chain (upload → link →
list) rather than a file-picker click-through, since Chrome's native file
dialog can't be driven by browser automation. Backend untouched — full
suite still 160/160.

**Scope note:** context images are read/write on their own now, but the
*existing* review overlay's "context images render in-page and get their
own highlight box like any other segment" claim (an `ImageReview.tsx` code
comment predating this phase) was not independently re-verified — it
depends on the reviewed page's own DOM already carrying a `data-tu-id`-tagged
`<img>` for that context image, which no target app in this repo's fixtures
does yet.

### Model Discovery, Locale Pickers, Analytics, CSV Import, Authenticated Crawl (Phase 18)

Six mostly-independent asks bundled into one pass: live model discovery for
every multi-model provider, a shared locale picker everywhere a language
was free-text before, Dashboard promoted to its own top-level Analytics
segment with actual charts, CSV added to Content Creation's file import,
and an opt-in authenticated crawl/fetch mode for Audit and Review's Any-URL
reviewer.

| Feature | Status | Notes |
|---------|--------|-------|
| `GET /api/v1/models/{provider}` | ✅ | Reads live from the provider — Ollama's `/api/tags`, LMStudio/vLLM/OpenAI's `/v1/models`, Gemini's `/v1beta/models`, Anthropic's Models API — not a hardcoded list. Covers all six providers with more than one selectable model (the three local servers AND Claude/OpenAI/Gemini, each of which ships multiple generations/sizes — a first pass of this scoped it to "local servers only" until corrected mid-build) |
| `ModelPicker.tsx` | ✅ | Provider dropdown + a second model dropdown that only appears (and only live-fetches) for a discoverable provider; degrades to "Default" with an inline error if discovery fails (missing API key, server not running) rather than blocking the picker |
| `TranslateRequest.model`, `RedriveRunRequest.scoring_model`/`redrive_model`, `EvaluateRequest.model` | ✅ | Threaded through `get_translation_backend()`/`get_scorer()` down to each backend/scorer's constructor |
| `LocaleSelect.tsx` + `data/locales.ts` | ✅ | Top 10 most-spoken languages (by total speakers, not market size) pinned above a broader ~35-language list; every free-text language `<input>` across Create Content, Documents, Image Review, Review, Redrive Console, Vendor Scorecard, Consistency, Style Guides, and Audit replaced with it. `variant="language"` for Audit's bare-subtag `primary_language`; `blankLabel` for "blank = all" filter fields |
| Dashboard → Analytics | ✅ | Promoted out of Quality Review's tab bar into its own 4th top-level segment (`App.tsx`) and renamed — its numbers aggregate across all three other segments, never really belonged nested under just one of them. Added a 4th stat card (Projects, previously fetched but unused) |
| `BarChart.tsx`, `DonutChart.tsx` | ✅ | Hand-rolled, dependency-free (div-width bars; SVG stroke-dasharray donut) — Analytics had zero charts before this, just numbers and a plain `<ul>` |
| CSV import | ✅ | `DocumentFormat.CSV`, `_parse_csv_blocks()` — one `TranslationUnit` per row (not blank-line blocks like text/md), taken from an optional `source_column` (defaults to the first column). `DocumentsPage.tsx` accepts `.csv` alongside `.txt`/`.md` |
| Authenticated crawl/fetch | ✅ | `crawl_site()`/`fetch_and_render()` gained optional `auth_username`/`auth_password` (HTTP Basic Auth) and `auth_cookie` (raw Cookie header), applied via a Playwright `BrowserContext` built once per crawl/fetch. **Anonymous remains the default and is unchanged** — every field omitted reproduces the exact prior behavior. Not a login-form-driving bot: "bring your own already-authenticated session," the standard pattern for this. Deliberately never persisted — accepted on `AuditRunRequest`/`GET /pages/render`'s query params, never written to the `SiteAudit` DB model |
| CMS push/pull content API | ✅ | Built in Phase 20 below (Strapi) |

**Bug found via live testing, not code review:** the model-discovery scope
above started as "Ollama/LMStudio/vLLM only" — corrected mid-implementation
once it was pointed out that Claude and OpenAI also ship multiple
selectable models, not just the three local servers. `_MODEL_OVERRIDABLE`
and the `/api/v1/models/{provider}` endpoint both cover all six now;
DeepL/Google Translate/MS Translator remain excluded (genuinely one
endpoint each, nothing to discover).

**Verified live and via curl, not just typecheck/build:** `GET /api/v1/
models/ollama` against a real local Ollama instance (returned the actual
four pulled models); `GET /api/v1/models/deepl` (correctly 400s, no model
list) and `/models/claude` (correctly 400s, no `ANTHROPIC_API_KEY` set);
`model` overrides confirmed reaching every one of the six backend/scorer
constructors directly in Python. CSV import verified end-to-end via curl
(a 3-row/3-column fixture → 2 `TranslationUnit`s from the `source_text`
column only, `key`/`notes` correctly ignored). The authenticated-crawl path
has a dedicated test (`test_audit_run_anonymous_vs_authenticated_crawl`,
`tests/test_audit.py`) against a real local HTTP-Basic-Auth-gated fixture
server — anonymous sees a 401, authenticated sees the real 200 page,
proving the credentials actually reach Playwright's browser context, not
just that omitting them leaves the existing anonymous path unaffected
(which the other 22 real-browser Page/Audit tests already covered). Full
suite 161/161 passing (160 prior + 1 new). Frontend: `tsc -b --force` and
`npm run build` both clean.

**Discovered while running the app locally, not a code bug:** this repo's
`docker-compose`-built `content-provenance-app-1` container is a baked
image with no live-reload — every backend edit in this phase required
switching to a local `uvicorn --reload` process on the same port instead.
Worth documenting for the next session: `docker compose up` is fine for
just running the app, but active backend development should run
`uvicorn app.main:app --reload --port 8001` directly (per this repo's own
README) rather than assuming the Docker container picks up edits.

### JSON Provenance Export/Import (Phase 19)

The JSON peer of XLIFF export/import (Phase 2) — same self-contained-
document idea (translation text + the complete embedded provenance chain,
single-unit or whole-project), same `ingest_events` ledger, but JSON
instead of XML. Distinct from the pre-existing `GET /provenance/{id}/
prov-json`, which only ever serialized the bare PROV bundle (no source/
target text, no deployments, no version history, no import counterpart).

| Feature | Status | Notes |
|---------|--------|-------|
| JSON document build/parse (`app/provenance_json/json_service.py`) | ✅ | `model.model_dump(mode="json")` does the real serialization — no XLIFF-style note-based key=value packing needed. Snake_case throughout, matching every other JSON response in this API |
| `GET /api/v1/json/{unit_id}`, `/project/{project_id}`, `/{unit_id}/preview` | ✅ | `app/api/json_export.py` — no caching table (unlike `xliff_documents`); built fresh from current DB state every call, since JSON serialization has no XML-pretty-print cost to amortize |
| Lenient import of plain/minimal JSON (`app/provenance_json/json_import.py`) | ✅ | Accepts this system's own extensive shape, a bare `{"units":[...]}` wrapper, a bare array, or a single bare unit object; alias field names (`sourceText`/`source`/`text` etc.) tolerated. Provenance is always rebuilt fresh server-side — importing a minimal file and exporting it back out is how a plain file becomes "the extensive version with the provenance metadata" |
| `POST /api/v1/json/import`, `GET /api/v1/json/ingest-log` | ✅ | `app/api/json_import.py` — the ingest-log route is a passthrough to the same ledger XLIFF's `/api/v1/xliff/ingest-log` already exposes (`IngestEvent.format` already distinguishes `"xliff"`/`"json"`), not a second ledger |

16 new tests (`tests/test_json_export.py`), full suite 177/177 passing.

### CMS Integration API — Strapi (Phase 20)

The "CMS push/pull content API" flagged since Phase 18 (see below) —
pushes a finished translation + its full provenance record into an
external CMS entry, and pulls a field's current value back out to seed a
new translation. Provider-abstracted the same way translation backends
are (`TranslationBackend` / `get_translation_backend`): Strapi is the only
working provider, Directus and Payload — the strongest other FOSS,
REST-based, natively multilingual CMSs — are prepared for but not built.

| Feature | Status | Notes |
|---------|--------|-------|
| `CMSIntegration` ABC + `get_cms_integration()` factory | ✅ | `app/core/integrations/base.py` / `factory.py` — `locale` optional on both push/pull. Selecting `directus`/`payload` fails loudly with what's missing (not implemented yet) rather than silently falling through to Strapi |
| `StrapiIntegration` | ✅ | `app/core/integrations/strapi.py` — raw `httpx`, no SDK. Handles both Strapi v4 (`data.attributes`-nested) and v5 (flat) response shapes; `?locale=` query param |
| `push_translation_to_cms` / `pull_source_from_cms` (`app/core/cms_service.py`) | ✅ | Push writes the translated field + a `content_provenance` field (the full `ProvenanceRecord`) in one request, then records a `context=cms` `DeploymentRecord` and rebuilds the unit's provenance to include it — same pattern `translations.record_deployment` already uses. Pull only fetches text — deliberately does not create a `TranslationUnit` itself; hand the result to `POST /api/v1/translations` |
| `DeploymentContext.CMS` | ✅ | Plain string column, no migration needed |
| `POST /api/v1/integrations/cms/push`, `GET /pull`, `GET /status` | ✅ | `app/api/integrations.py` |
| Local Strapi for testing (`docker-compose --profile cms`) + `scripts/bootstrap_strapi.py` | ✅ | Verified live, not just written: built the image, booted a real Strapi 5.52.0, ran the bootstrap script end-to-end (admin registration, content-type creation via the Content-Type Builder API, API token, demo entry), then `--verify` created a real translation through this app, pushed it via `POST /api/v1/integrations/cms/push`, and read the Strapi entry back directly to confirm both the translated text and the full `content_provenance` field landed correctly. Caught and fixed two real bugs this way: the Content-Type Builder payload shape (`singularName`/`pluralName`/`displayName` go directly on `contentType`, not nested under `info` as in Strapi v4) and the API token response field (`accessKey`, not `accessToken`) |
| Sample Strapi-backed website (`demo/strapi-site/index.html`) | ✅ | Reads the demo content type straight from Strapi's public REST API (bootstrap script now also grants the Public role `find`/`findOne` on it — no token in client-side code). Renders live CMS text + a provenance panel per entry. Verified in a real browser: pushed a translation via curl, watched the page pick it up on its own 8s auto-refresh with no reload. Caught and fixed one real bug this way — the naive re-render-from-scratch on each refresh snapped an opened provenance `<details>` shut; now preserved by entry id across re-renders |
| `demo-site` as its own docker-compose service/port (4321), not a route on `app` | ✅ | Originally mounted at `app`'s own `/demo/` path — moved after it compounded the exact `app`-container-vs-local-`uvicorn` port contention already documented in Phase 18's notes above, and because an independent website belongs on its own port regardless. Standalone nginx container serving `demo/strapi-site/` as static files; `app/main.py` no longer mounts it at all |

9 new tests (`tests/test_cms_integration.py`, offline-stub convention —
no live Strapi needed for the suite), full suite 177/177 passing (Phase
19 + 20 tests are additive to the same run).

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
| CMS push/pull content API (Strapi) | ✅ | Built in Phase 20 — see the built-features section above. Distinct from the TMS connectors above (a CMS publishes content, a TMS manages the translation workflow around it) |
| Directus / Payload CMS connectors | 💡 | `CMSIntegration`/`get_cms_integration()` (Phase 20) already shape the provider contract for these — see `app/core/integrations/factory.py`'s docstrings on each for exactly what a real implementation needs (Directus: no universal `locale` param, needs a translations-junction-collection mapping; Payload: a near-mechanical port of `StrapiIntegration`) |
| WordPress / Contentful / Sanity connectors | 💡 | Not evaluated against the `CMSIntegration` shape yet — WordPress's multilingual support in particular is plugin-bolted (Polylang/WPML), not core, unlike Strapi/Directus/Payload |

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
