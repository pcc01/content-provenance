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

Beyond tracking provenance, the system runs a **threshold-quality redrive
loop**: score every translation (deterministic checks, falling back to a
pluggable Claude/Ollama scorer), automatically resend anything below a
threshold for retranslation, and record the whole thing — new version, new
provenance, `wasRevisionOf` link back to what it replaced — with an optional
human-in-the-loop gate before any redrive actually goes live. Reviewing that
content happens in-context: the **Review Shell** overlays the real rendered
page with clickable highlight boxes instead of a segment-grid TMS view (see
[Run the review environment](#run-the-review-environment-review-shell)
below).

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
- PostgreSQL, reachable (or Docker, to run it via `docker-compose up postgres`) — the system of record, not optional
- Node.js 18+ / npm — only needed for the Review Shell (`frontend/`) and its demo fixture, not the API server itself
- A Playwright-managed Chromium install — only needed for Phase 8's "review any URL" fetch mode (`playwright install chromium`, see below)

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/ai-translation-provenance.git
cd ai-translation-provenance

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# One-time: install the headless browser Phase 8's fetch+rewrite mode uses
# to render arbitrary URLs (skip this if you'll only use the cooperative
# SDK-tagging model, or Documents/text-Markdown review)
playwright install chromium

# Copy environment config
cp .env.example .env

# Start Postgres (or point .env at your own — see .env.example)
docker-compose up -d postgres

# Apply migrations
alembic upgrade head
```

### Run (development — mock translation)

```bash
uvicorn app.main:app --reload --port 8001
```

> Port 8001, not the default 8000 — chosen to avoid colliding with another
> project's stack that may already be using 8000/5432/6379/3000/9090 on the
> same machine. Use whatever port is free on yours; just keep it consistent
> with `frontend/vite.config.ts`'s proxy target and `frontend/demo-target`'s
> `VITE_API_BASE` if you change it.

Open http://localhost:8001/docs for the interactive API explorer. The review
UI now lives in `frontend/` (a Vite+React app, see its own dev instructions)
rather than being served as a static dashboard from this server.

### Run with Anthropic Claude translation

```bash
# Set your key in .env
ANTHROPIC_API_KEY=sk-ant-...
TRANSLATION_PROVIDER=anthropic

uvicorn app.main:app --reload --port 8001
```

> PostgreSQL is the system of record for everything (translations, provenance,
> XLIFF documents, quality scores, redrive runs, image assets). Re-run
> `alembic upgrade head` after pulling any change that touches
> `alembic/versions/`.

### Run with Docker

```bash
# App + PostgreSQL (mock translation) — host ports 8001 (app) / 5433 (postgres),
# deliberately offset from 8000/5432 in case another project's stack is
# already using those on the same machine
docker-compose up

# With persistent Qdrant vector store
docker-compose --profile search up

# Full stack (Qdrant + Elasticsearch too)
docker-compose --profile full up
```

### Run the review environment (Review Shell)

The review UI is a separate Vite+React app, not served as a static file from
the API server. In development, run it alongside the backend:

```bash
cd frontend && npm install && npm run dev       # Review Shell — http://localhost:5173
```

Once (or after changing `review-sdk/overlay.ts`), build the standalone SDK
bundle Phase 8's fetch+rewrite pages inject — `npm run dev`/`npm run build`
don't do this for you automatically:

```bash
cd frontend && npm run build:sdk                # frontend/review-sdk/dist/overlay.js
```

To exercise the in-context overlay end-to-end, also run the demo fixture it
iframes (a minimal page tagged with the review SDK — see
[`frontend/review-sdk/`](frontend/review-sdk)):

```bash
cd frontend/demo-target && npm install && npm run dev   # http://localhost:5174
```

Open the Review Shell, enter the demo target's URL (defaults to
`http://localhost:5174`), and click "Load page" — translated elements get
highlighted directly on the rendered page; click one to open the review
drawer (source/target, version history, provenance, notes).

Alternatively, switch the Review tab to **"Any URL"** mode and paste any
URL — no demo fixture, no SDK tagging, no app changes at all. This routes
through Phase 8's fetch+rewrite loader (`GET /api/v1/pages/render`), which
renders the page with a headless browser, harvests its text server-side,
and serves back a tagged copy the same overlay reviews identically. This is
the path to use against a real app you don't want to (or can't) modify.

Adopting the SDK in a real app instead of the demo fixture just means wrapping translated
strings with `data-tu-id` tag props — see `frontend/review-sdk/reviewTagProps.ts`
and `useReviewT.ts`.

For production, `npm run build` in `frontend/` produces `frontend/dist/`
(and, as part of the same script, `frontend/review-sdk/dist/overlay.js`),
which `app/main.py` serves directly — no separate frontend server needed.

---

## API Reference

### Translations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/translations/` | Submit content for translation — returns translation + provenance IDs |
| `GET`  | `/api/v1/translations/` | List all translation units (filter by language, method, status) |
| `GET`  | `/api/v1/translations/batch?ids=a,b,c` | Bulk lookup with latest quality score — what the review overlay uses to score a whole page in one call |
| `GET`  | `/api/v1/translations/{id}` | Get a specific translation unit |
| `GET`  | `/api/v1/translations/{id}/versions` | Full edit history (initial / human_edit / import / redrive / revert) |
| `POST` | `/api/v1/translations/{id}/versions/{version_id}/revert` | Phase 9: restore an earlier version's text as a new version (never rewrites history) |
| `POST` | `/api/v1/translations/{id}/deploy` | Record a new deployment location |
| `PUT`  | `/api/v1/translations/{id}/review` | Mark as human-reviewed |
| `GET`  | `/api/v1/translations/stats` | Aggregated statistics |
| `GET`/`POST` | `/api/v1/translations/{id}/notes` | Review notes thread (threaded via `parent_id`) |
| `PUT`  | `/api/v1/translations/{id}/notes/{note_id}/resolve` | Mark a note resolved/unresolved |

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

### XLIFF Export & Import

Every XLIFF document entering (import) or leaving (export) the system is
logged in an ingest ledger — the literal "track everything entering and
leaving the system" record.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/v1/xliff/{id}` | Download XLIFF 2.0 file with embedded PROV metadata (incl. per-version history notes) |
| `GET`  | `/api/v1/xliff/{id}/preview` | Preview XLIFF as text |
| `GET`  | `/api/v1/xliff/project/{id}` | Export full project as a single XLIFF document |
| `POST` | `/api/v1/xliff/import` | Ingest an external XLIFF 2.0 document (multipart `file` + `source_system`) — creates/updates units and their version history; synthesizes minimal provenance if the file carries none |
| `GET`  | `/api/v1/xliff/ingest-log` | The entering/leaving ledger |

### Threshold-Quality Redrive

Score everything in scope, then redrive (retranslate) whatever falls below a
threshold — the core loop this system is built around, modeled on an offline
QE-scorer → threshold → MT-fallback-chain pipeline.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/redrive/runs` | Create + run a redrive pass (`threshold`, `scope`, `require_human_approval`, `scoring_provider`) |
| `GET`  | `/api/v1/redrive/runs/{id}` | Status/results of a run |
| `POST` | `/api/v1/redrive/runs/{id}/items/{item_id}/approve` | Human-in-the-loop: apply a proposed redrive |
| `POST` | `/api/v1/redrive/runs/{id}/items/{item_id}/reject` | Human-in-the-loop: decline a proposed redrive |
| `GET`  | `/api/v1/redrive/preview` | Dry-run forecast — how many units a threshold would catch, no writes/spend |
| `GET`  | `/api/v1/redrive/queue` | Units currently below a threshold, worst-first |

Scoring runs deterministic free checks first (untranslated/garbage/placeholder
issues, wrong script, HTML tag/number mismatches — ported from
peripateticware's `qa_review_llamacpp.py`), falling through to a configured
model scorer (`SCORING_PROVIDER=claude` or `ollama`) only for pairs those
don't resolve. Set `require_human_approval: true` on a run to have redrives
proposed but not applied until a reviewer calls the approve/reject endpoints
— useful for organizations that want AI-driven changes gated by a human even
when the score/threshold decision itself is automated.

### Image Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/images/` | Upload an image (`kind=context\|translatable`) |
| `GET`  | `/api/v1/images/{id}` / `/{id}/file` | Metadata / raw file bytes |
| `POST` | `/api/v1/images/{id}/context-link` | Attach a context screenshot to a translation unit |
| `GET`  | `/api/v1/images/context-links/{unit_id}` | Context images linked to a unit |
| `POST` | `/api/v1/images/{id}/localize` | Start localizing a source image (optionally with the target file immediately) |
| `PUT`  | `/api/v1/images/localize/{itu_id}/target` | Attach/replace the localized target image |
| `GET`  | `/api/v1/images/localize/{itu_id}` | An image translation unit's status + linkage |

Context images (screenshots showing a text segment in its real layout) render
inline in the review overlay like any other segment. Translatable images
(banners, graphics) get their own provenance chain reusing the same PROV-DM
builder as text (`SourceImage`/`TranslatedImage` entities).

### Documents (plain text / Markdown)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/import` | Upload a `.txt`/`.md` file — split into paragraph/block segments, translated immediately |
| `GET`  | `/api/v1/documents/{id}` | Document metadata |
| `GET`  | `/api/v1/documents/{id}/segments` | Ordered segments for a target language |

Each paragraph/block of an imported document becomes an ordinary
`TranslationUnit` (tagged `{document_id, position}` in its metadata), so it
gets the same translation/scoring/redrive/provenance treatment as any other
unit. The Review Shell's "Documents" tab uploads a file and hands back a
ready-made target URL/route/locale for the "Review" tab — the document
renders as its own `data-tu-id`-tagged page at `/documents/{id}`, served
from the Review Shell's own origin, so the existing overlay SDK reviews it
with no changes. PDF/PowerPoint/DOCX are tracked but not yet designed — see
`ROADMAP.md`.

### Pages (review any URL, no app changes required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/pages/render` | Fetch (or re-serve/reconstruct) a URL, harvested/tagged/rewritten and ready to review |
| `GET` | `/api/v1/pages/history` | Timeline of points where something on the page changed |
| `GET` | `/api/v1/pages/diff` | Which segments differ between two points in time |
| `POST` | `/api/v1/pages/harvest` | Phase 10: match/create units for an already-harvested item list — what the browser extension's content script calls, no headless browser involved |
| `GET`/`POST` | `/api/v1/pages/notes` | Page-level notes thread (not tied to one segment) |
| `PUT` | `/api/v1/pages/notes/{note_id}/resolve` | Mark a page-level note resolved/unresolved |
| `GET` | `/api/v1/pages/pending` | Every unapproved human-drafted proposal on a page — the editor view's data source |
| `POST` | `/api/v1/redrive/propose` | A reviewer's own draft, filed as a `PENDING_APPROVAL` item through the same human-in-the-loop machinery as a redrive |
| `POST` | `/api/v1/redrive/items/bulk-approve` | Approve several pending items (proposals or redrives) at once |

`render` query params: `url` (required), `target_language` (required),
`source_language` (default `en-US`), `method` (default `ai`), `refresh`
(force a live re-fetch instead of reusing the latest cached snapshot),
`as_of` (Phase 9 — reconstruct the page as it looked at this timestamp
instead of the current live version). `history`/`diff` take `url` +
`target_language` (`diff` also takes `from_ts`/`to_ts`).

This is the non-cooperative counterpart to the SDK-tagging model above —
`app/core/page_fetch.py` renders the URL with a headless browser
(Playwright), harvests its visible text into `TranslationUnit`s keyed by a
stable content hash (so re-fetches reuse history rather than duplicating
it), tags and rewrites a copy of the DOM (absolute asset URLs, target-locale
text, the review-sdk script injected), and serves it same-origin. The
Review tab's "Any URL" mode points `ReviewFrame` at this endpoint instead of
an SDK-tagged app — paste any URL, no source changes needed on that end at
all. See `ROADMAP.md`'s "Non-Cooperative Page Review" section for the full
design and known limitations (anonymous fetches, no SSRF hardening since
reviewing your own localhost apps is the point, `dom_path` drift across
redesigns).

Phase 9 adds time-travel on top, with no new snapshot-storage system —
`app/core/page_history.py` reconstructs "page as of time T" from the
existing `TranslationUnitVersion` history plus a `PageSnapshot` structural
template. The Review Shell's "History" panel (fetch mode only) lets you
load a past version or diff two points; reverting a segment (in
`SegmentDrawer`'s History tab) is `POST /api/v1/translations/{id}/versions/
{version_id}/revert` — restores old text as a *new* version, never rewrites
history. See `ROADMAP.md`'s "Page History / Time Travel" section for the
full design.

Phase 10 adds a browser extension (`frontend/extension/`, Manifest V3) that
runs this same harvest/match engine against a real tab's live DOM instead of
an anonymous fetch — cookies, session, and client-side routing all work for
free. It tags matched elements with `data-tu-id` but never swaps a live
page's text (unlike the fetch mode above). A reviewer using either mode can
also type their own draft for a segment (`SegmentDrawer`'s "Propose
translation") or leave a page-level note; proposals show as a dashed-purple
highlight until approved individually or all at once via the
`PendingChanges.tsx` editor view. See `ROADMAP.md`'s "Live-Session Bridge"
section for the full design, and `frontend/extension/README.md` for how to
load the extension.

### Site Audit (Phase 11/12 — i18n/l10n/compliance review of a third-party site)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/audit/runs` | Crawl a site and run the enabled checks — runs synchronously, returns the completed (or failed) audit |
| `GET`  | `/api/v1/audit/runs` | List past audits |
| `GET`  | `/api/v1/audit/runs/{id}` | Status + finding counts by check/severity |
| `GET`  | `/api/v1/audit/runs/{id}/pages` | The crawled-page inventory |
| `GET`  | `/api/v1/audit/runs/{id}/findings` | Findings, filterable by `check`/`severity`/`page_id` |
| `GET`  | `/api/v1/audit/runs/{id}/export` | Plain-text report download |
| `GET`  | `/api/v1/audit/runs/{id}/report.pdf` | Branded PDF report download (logo, executive summary, findings by check) |

**POST /api/v1/audit/runs — request body**

```json
{
  "root_url": "https://example.com",
  "primary_language": "en",
  "max_pages": 40,
  "checks": [
    "mixed_locale", "rtl_readiness", "icu_i18n", "privacy",
    "text_expansion", "font_coverage", "hreflang", "cookie_consent",
    "placeholder_leak", "locale_format"
  ]
}
```

Distinct from every other capability in this system: it audits a
THIRD-PARTY site from the outside, not this system's own translations, and
doubles as a consulting-practice tool (international-expansion readiness
audits — the branded PDF report is meant to be handed to a client).
`app/core/audit/crawler.py` does a Playwright-based (client-rendered SPA
content included) same-domain crawl, reusing Phase 8's `robots.txt` check.
Ten pluggable checks in `app/core/audit/checks/` — mixed-locale detection,
RTL/logical-CSS-property readiness, ICU/i18n-tooling detection (including
literal leaked ICU MessageFormat syntax in rendered text), privacy-policy
language-mismatch + region-aware regulatory review, text-expansion/
truncation risk, font/script coverage, hreflang/SEO localization,
cookie-consent detection, untranslated-placeholder leakage, and hardcoded
locale-format assumptions — write structured findings rather than a
single flat report file. Region→regulation mapping
(`app/core/audit/regions.py` + `app/core/audit/data/jurisdictions/*.json`)
uses real jurisdiction data ported from the user's own privacy-compliance
engine built for peripateticware — the DATA only, not a live dependency on
that project's server. The Review Shell's "Audit" tab
(`AuditPage.tsx`/`AuditReport.tsx`) starts runs and browses findings
grouped by check with severity coloring; a finding's "Review this page"
button hands off directly into the existing fetch-mode review for that
URL; `app/core/audit/report.py` (reportlab) generates the branded PDF. See
`ROADMAP.md`'s "Site I18n & Compliance Audit Toolkit" and "Consulting-Grade
Checks, Regulatory Data & PDF Report" sections for the full design.

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
# Run tests (needs Postgres reachable — docker-compose up postgres, or point
# POSTGRES_*/DATABASE_URL at your own; the schema is dropped and recreated
# once per test session so runs are deterministic)
PYTHONPATH=. pytest tests/ -v

# New migration after changing app/core/db/models.py
alembic revision -m "describe the change"
alembic upgrade head

# Lint
pip install ruff
ruff check app/ tests/

# Frontend type-checking (no separate test suite yet — covered by manual
# browser verification of the review flow)
cd frontend && npx tsc -b
cd frontend/demo-target && npx tsc -b
```

---

## Project Structure

```
content-provenance/
├── alembic/                        # Schema migrations (source of truth for the DB schema)
│   └── versions/                   # 0001_initial … 0011_site_audits
├── app/
│   ├── main.py                     # FastAPI app, lifespan, router registration, serves frontend/dist/
│   ├── api/
│   │   ├── translations.py         # CRUD + deploy + review + batch + versions
│   │   ├── notes.py                # Review notes thread
│   │   ├── provenance.py           # PROV record, PROV-JSON, PROV-N, lineage
│   │   ├── search.py               # Haystack semantic/BM25 search
│   │   ├── xliff_export.py         # XLIFF 2.0 download and preview ("leaving" the system)
│   │   ├── xliff_import.py         # XLIFF 2.0 ingestion + the entering/leaving ledger ("entering")
│   │   ├── redrive.py              # Threshold-quality redrive runs, preview, queue, human-in-the-loop approve/reject
│   │   ├── images.py               # Image asset upload, context-linking, localization
│   │   ├── documents.py            # Phase 7a: text/Markdown document import + segments
│   │   ├── pages.py                # Phase 8/9/10: fetch+rewrite review, page history, page-level notes, pending-proposals list
│   │   └── audit.py                # Phase 11: site i18n/l10n/compliance audit runs + findings
│   ├── core/
│   │   ├── config.py               # Environment-based settings
│   │   ├── database.py             # Thin public interface (get_db/init_db) over db/repository.py
│   │   ├── db/                     # Postgres persistence layer
│   │   │   ├── models.py           # SQLAlchemy ORM models
│   │   │   ├── session.py          # Async engine/session factory
│   │   │   └── repository.py       # PostgresRepository — all persistence logic
│   │   ├── scoring/                # Quality scoring — deterministic + pluggable model scorers
│   │   │   ├── deterministic.py    # Free floor-checks (ported from peripateticware's QE scorer)
│   │   │   ├── claude_scorer.py    # Claude-as-judge (MQM-style)
│   │   │   ├── ollama_scorer.py    # Local Ollama QE model
│   │   │   └── factory.py          # CompositeScorer selection
│   │   ├── redrive/                # Threshold-quality redrive engine
│   │   │   ├── engine.py           # RedriveEngine — score, threshold, redrive, human-in-the-loop
│   │   │   ├── ledger.py           # DB-backed per-provider usage budget
│   │   │   └── propose.py          # Phase 10: a human's own draft, filed as an ad-hoc PENDING_APPROVAL item
│   │   ├── prov_builder.py         # W3C PROV-DM graph builder (text + image), PROV-JSON
│   │   ├── page_fetch.py           # Phase 8: Playwright fetch, harvest/match/tag/rewrite an arbitrary URL
│   │   ├── page_history.py         # Phase 9: point-in-time reconstruction, diff, timeline — no new snapshot storage
│   │   ├── audit/                  # Phase 11/12: third-party site i18n/l10n/compliance audit
│   │   │   ├── crawler.py          # Playwright BFS crawl — text/links/forms/hreflang/stylesheet+script bodies per page
│   │   │   ├── runner.py           # Orchestrates crawl -> persist pages -> run checks -> persist findings
│   │   │   ├── regions.py          # Phase 12: region -> regulation mapping, ported from peripateticware's privacy engine (data only)
│   │   │   ├── report.py           # Phase 12: branded PDF report (reportlab)
│   │   │   ├── data/jurisdictions/ # Phase 12: 9 ported jurisdiction JSON files (GDPR, CCPA, LGPD, ...)
│   │   │   └── checks/             # mixed_locale, rtl_readiness, icu_i18n, privacy, text_expansion, font_coverage, hreflang, cookie_consent, placeholder_leak, locale_format — pure functions over crawled data
│   │   ├── haystack_pipeline.py    # Haystack 2.x indexing and search
│   │   └── translation_backends.py # Pluggable: Mock / Anthropic / DeepL / Google
│   ├── models/
│   │   └── schemas.py              # Pydantic models — PROV, XLIFF, Translation, Deployment, QualityScore, RedriveRun, ImageAsset, ReviewNote…
│   ├── xliff/
│   │   ├── xliff_service.py        # XLIFF 2.0 generation/parsing with full embedded PROV + version history
│   │   └── xliff_import.py         # Import logic (create/update units from a parsed XLIFF doc)
│   └── static/branding/logo.png    # Phase 12: consulting-firm logo used in the PDF audit report
├── frontend/                       # Review Shell — Vite + React + TypeScript (replaces the old static dashboard)
│   ├── src/
│   │   ├── api/client.ts           # Typed fetch wrapper for the whole API
│   │   ├── components/             # ReviewFrame, SegmentDrawer, PageFlaggedList, PageHistory, PageNotes, PendingChanges, AuditReport, ProvenancePanel, QualityBadge, VersionHistory, NotesThread
│   │   └── pages/                  # ReviewPage, LiveReviewPage, RedriveConsole, ImageReview, DocumentsPage, DocumentViewer, AuditPage, SearchPage, Dashboard
│   ├── review-sdk/                 # The in-context overlay injected into a cooperative target app, or extracted for Phase 10's extension
│   │   ├── overlay.ts              # Highlight boxes, score/pending coloring, pluggable transport (postMessage or chrome.runtime)
│   │   ├── harvest.ts              # Phase 10: shared harvest/rewrite DOM walk — compiled once, used by both Playwright and the extension
│   │   ├── reviewTagProps.ts       # data-tu-id tagging primitive
│   │   ├── useReviewT.ts           # react-i18next binding shape for real-app adoption
│   │   ├── vite.sdk.config.ts      # Bundles overlay.ts to dist/overlay.js — served at /sdk-dist by
│   │   │                           # FastAPI for Phase 8's fetch+rewrite pages (never go through Vite's dev-transform)
│   │   ├── vite.harvest.config.ts  # Bundles harvest.ts to dist/harvest.js
│   │   └── dist/                   # Build output — `npm run build:sdk` (gitignored)
│   ├── extension/                  # Phase 10: Manifest V3 browser extension — reviews a real tab's live session
│   │   ├── background.ts           # Service worker relaying messages between the reviewed tab and the Review Shell's tab
│   │   ├── harvest-content-script.ts  # Injected on demand into the reviewed tab; tags elements, never swaps live text
│   │   ├── bridge-content-script.ts   # Injected into the Review Shell's own page; relays chrome.runtime <-> window.postMessage
│   │   └── popup.html / popup.ts   # Toolbar popup — target language, start/stop, mini notes panel
│   └── demo-target/                # Minimal fixture app the Review Shell iframes for local verification
├── docs/
│   └── architecture.svg            # System architecture diagram
├── tests/
│   ├── conftest.py                 # pytest fixtures, async client, per-session schema reset
│   ├── test_provenance.py          # Unit tests (models, XLIFF, PROV builder, DB)
│   ├── test_api.py                 # API integration tests — translations, provenance, XLIFF, redrive, notes, search
│   ├── test_redrive.py             # Redrive engine tests incl. human-in-the-loop
│   ├── test_images.py              # Image asset API tests
│   ├── test_documents.py           # Document import/segments API tests
│   ├── test_pages.py               # Page fetch/harvest/render + history/diff/as_of tests (real headless-browser render)
│   ├── test_revert.py              # Version revert API tests
│   ├── test_propose.py             # Phase 10: human-drafted proposal -> pending -> approve/reject tests
│   └── test_audit.py               # Phase 11/12: all 10 checks + PDF export against a local fixture site
├── .gitignore
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml              # dev / search / full profiles — host ports offset (8001/5433) to avoid collisions
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
