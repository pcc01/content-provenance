# Proposal: pgGraph + GraphRAG for LLM Localization Provenance

Status: ✅ Phase 13 and Phase 14 both built (backend/API — see `ROADMAP.md`
for the feature tables and the known frontend gap common to both). This
doc stays as the rationale/evaluation record — see `ROADMAP.md` for the
build-tracking feature tables and build order. One build-time correction
worth noting here: Phase 14's consistency checks did NOT end up wired into
`app/core/audit/`'s `SiteAuditCheck` framework as §9b sketched — that
subsystem audits crawled third-party site HTML, a different data domain
from this system's own `TranslationUnit`s, so consistency checking got its
own module (`app/core/consistency/`) instead.

**Decided:** §3/§4's Option A + Option 1 — plain relational graph tables
(`graph_nodes`/`graph_edges`, recursive CTEs), no Apache AGE for now,
everything in the existing `pgvector/pgvector:pg16` Postgres instance, no
second database. §9's persona walkthrough validated the direction and
added TMX import, the style/glossary vendor brief, and source-side voice
checking to Phase 13's scope, with the vendor scorecard and cross-document
consistency check sequenced into Phase 14. Next scenario pass happens
after both phases ship (per the user).

---

## 1. Why

Today the system tracks **what** was translated, **by what/whom**, **how**,
**when**, and **where deployed** — full W3C PROV-DM lineage, embedded in
XLIFF, scored for *accuracy* (MQM-style critical/major/minor errors in
`app/core/scoring/claude_scorer.py`).

It does **not** currently track or score:

- **Tone** (formal/casual, urgent/calm, ...)
- **Voice** (brand personality — "playful," "authoritative," ...)
- **Style adherence** (house style guide rules, formatting conventions)
- **Terminology/glossary consistency** across a document, page, or whole site
- **What context an LLM actually drew on** when it made a localization
  choice — today an AI translation is attributed to an *agent* (model +
  version), but nothing records *which style guide passage, prior
  translation, or glossary entry* informed a specific word choice

That last gap is the actual target. A quality *score* tells you a
translation is off-tone; it doesn't tell you *why*, or let you fix the
source of the drift (a stale style guide chunk, a missing glossary term, a
prior mistranslation the model pattern-matched against). Closing it means
retrieval — pulling the right style/voice/terminology context in front of
the model before/while it translates — and then **provenance over the
retrieval itself**, not just the output. That's what GraphRAG is for here:
not a chatbot feature, a *sourcing mechanism* whose sources become PROV
entities like everything else in this system.

---

## 2. Where this plugs into what already exists

| Existing piece | Relevance |
|---|---|
| `provenance_entities` / `provenance_activities` / `provenance_relations` (`app/core/db/models.py`) | Already a graph in disguise — entities/activities as nodes, relations as typed edges, just addressed by string id rather than FK. pgGraph formalizes this rather than replacing it. |
| `pgvector/pgvector:pg16` Postgres image (`docker-compose.yml`) | **Already deployed**, extension available, currently unused — `requirements.txt` has `pgvector` commented out and Haystack runs its own **in-memory** store (`app/core/haystack_pipeline.py`). This is the single biggest fact shaping the recommendation below: half the infra for a Postgres-native GraphRAG is already running idle. |
| `app/core/scoring/` (deterministic + Claude MQM scorer, `factory.py` composite) | Pattern to extend, not replace — a new `StyleAdherenceScorer` slots in beside `ClaudeQualityScorer` the same way. |
| `app/core/redrive/engine.py` | Threshold-quality redrive loop — style/tone score becomes a second threshold axis it can act on. |
| XLIFF `<note category="prov:...">` embedding (`app/xliff/xliff_service.py`) | Every unit is already a self-contained provenance artifact; style/voice/retrieval provenance extends the same note vocabulary, doesn't invent a new export path. |
| Documents (`app/api/documents.py`), Pages (`app/api/pages.py`), XLIFF import/export | The three granularities the user asked to cover — a paragraph/block, a page-URL, and an XLIFF `<unit>` are already three different front doors onto the *same* `TranslationUnit`/`TranslationUnitVersion` rows. GraphRAG context-tracking should attach at that shared layer, not be re-implemented three times. |

---

## 3. What "pgGraph" means here, concretely

There's no single product called "pgGraph" — the term covers a spectrum of
ways to make Postgres itself queryable as a graph. Three real candidates:

| Option | What it is | Fit here |
|---|---|---|
| **A. Relational graph tables** (recommended starting point) | Plain `graph_nodes` / `graph_edges` tables (FK-based, typed, JSON properties), traversed with recursive CTEs (`WITH RECURSIVE`). No new extension. | Directly generalizes the existing `provenance_entities/activities/relations` pattern. Alembic-native (plain `CREATE TABLE`), works with asyncpg/SQLAlchemy exactly like every other table in this codebase, zero new ops surface. Ceiling: recursive CTEs get unwieldy past ~4-5 hop traversals and can't do graph algorithms (community detection, weighted centrality). |
| **B. Apache AGE** | Postgres extension adding a real property-graph type + openCypher query language, coexisting with normal SQL tables in the same database/transaction. | Same DB, same backup, same transaction as everything else — attractive given "Postgres is the system of record, not optional" is a stated design principle. See §3a for version compatibility and the concrete effort/compromise comparison against Option A. |
| **C. Embedded graph engine (Kuzu)** | An in-process, file-based graph database (Cypher query language) bundled into the app process, no server. | No new docker-compose service, but a second storage engine to keep consistent with Postgres — every write becomes two writes. Newer/less battle-tested than AGE. |

**Recommendation:** start with **A**, add **B (AGE)** later only if a
specific query (e.g. "every style rule that transitively influenced any
unit derived from source X") proves too painful as a recursive CTE. This
also de-risks the GraphRAG decision below, since Option 1 there works
identically on top of A or B.

**One database, not two, either way.** Both A and B are additions *inside*
the existing Postgres instance — every table in `app/core/db/models.py`
(`translation_units`, `provenance_entities`, `xliff_documents`,
`quality_scores`, `redrive_runs`, `image_assets`, `review_notes`,
`documents`, `page_snapshots`, `site_audits`, the ingest ledger, all 20+
others) stays exactly as it is, untouched, in the same database, same
transactions, same `AsyncSession`. AGE doesn't replace Postgres — it's a
Postgres extension, so `CREATE EXTENSION age;` runs against the same
`provenance` database this project already has; the graph lives alongside
the relational tables, not instead of them. **This only becomes a
two-database question under §4 Option 2** (Neo4j) — and even there,
Postgres remains the system of record for everything above; Neo4j would be
a *derived, additional* index, not a replacement. Wholesale replacing
Postgres with a native graph database for *everything* (including things
that are fundamentally relational and benefit from it — the provider
usage ledger's atomic counters, XLIFF document storage, page-snapshot
history, threaded review notes, checksum-indexed image assets) isn't on
the table as a serious option: it would mean re-implementing the entire
existing persistence layer with no corresponding benefit, since none of
those features are graph-shaped. Net: **A or B, no second database, and no
database replacement — just an addition to the one you already have.**

### 3a. Apache AGE: version compatibility and effort/compromise detail

**Compatible with the current stack.** AGE officially supports PostgreSQL
16 — the `PG16` release branch (`release/PG16/v1.6.0`) has existed since
Sep 2025, alongside PG14/15/17/18 branches. `docker-compose.yml`'s
`pgvector/pgvector:pg16` image is itself just `postgres:16-bookworm`
(Debian) with pgvector layered on via a build-and-install Dockerfile step
— AGE would be added the same way (a second, near-identical layer:
`postgresql-server-dev-16` + build AGE's `PG16` branch + `make install`),
not a conflicting or exotic install path. AGE and pgvector are independent
extensions and don't contend for anything — no incompatibility between
them. One honest caveat: AGE's own release tags are still labeled `-rc0`
even for branches that have been the de facto stable target for a year
(e.g. `PG16/v1.6.0-rc0`, Sep 2025) — a signal the project's release
process is informal, not that the code itself is unstable, but worth
knowing going in. Windows-native builds aren't supported/documented — a
non-issue here since Postgres already only runs inside Docker in this
project.

**Effort comparison.** Both paths need the same *domain* schema work
(style guide, glossary, unit↔rule/term edges) — the difference is entirely
in the plumbing around it:

| | Plain tables (Option A) | Apache AGE (Option B) |
|---|---|---|
| Docker image | No change — today's `pgvector/pgvector:pg16` as-is | New Dockerfile layer to build/install AGE (~half day; low risk, mirrors the pgvector layer already proven in this exact base image) |
| Connection setup | None — same asyncpg/SQLAlchemy session as every other table | Every new connection must `LOAD 'age'; SET search_path = ag_catalog, "$user", public;` before querying — needs a connection-init hook in `app/core/db/session.py` (~half day) |
| Schema/migrations | `op.create_table(...)` in `alembic/versions/`, identical to the 13 migrations already there | No Alembic operator support — graph/label DDL goes through raw `op.execute("SELECT create_graph(...)")` / `create_vlabel`/`create_elabel` calls; same amount of *schema design* work, different (less declarative) mechanism |
| ORM / query layer | `GraphNodeRow`/`GraphEdgeRow` SQLAlchemy models, queried with `AsyncSession` like everything in `PostgresRepository` today | Cypher via `SELECT * FROM cypher('graph_name', $$ ... $$) AS (result agtype)` — returns Postgres's `agtype`, which needs a parsing/casting helper (~half–1 day) since it isn't a type SQLAlchemy/asyncpg know natively |
| Two query languages in one codebase | No — everything stays SQL/ORM | Yes, by design — normal SQLAlchemy everywhere else, raw Cypher strings confined to a new `app/core/graph/` module |
| **Rough one-time integration cost before writing a single real query** | ~0 (uses existing patterns) | **~2–3 extra days** of Dockerfile/connection/agtype plumbing |

### 3b. What "a hop" means here, concretely

A **hop** is one traversal across one edge/relationship, from one node to
the node next to it. It's a way of talking about *how far away, and
through how many relationships,* the thing you want is from the thing you
already have — using the schema this proposal actually calls for (§5):

- **1 hop:** `Unit —[appliedRule]→ StyleGuideRule` — "which rule did this
  unit apply, directly." One edge, one join.
- **2 hops:** `Unit —[appliedRule]→ StyleGuideRule —[partOf]→ StyleGuide`
  — "which *style guide* (not just which rule) governed this unit." Two
  edges, two joins (or one JOIN-of-a-JOIN).
- **3 hops:** `Unit —[appliedRule]→ StyleGuideRule —[partOf]→ StyleGuide
  —[supersedes]→ StyleGuide(older)` — "which now-outdated style guide
  version indirectly shaped this unit, via a rule nobody's updated yet."
  Three edges — the kind of question that motivates the redrive/consistency
  features in §5–§7.
- **Fixed vs. variable hop count:** the examples above are *fixed* — you
  know in advance it's exactly 2 or exactly 3 edges, so a specific number
  of `JOIN`s (or a recursive CTE with a hard depth limit) handles it fine
  in plain SQL. A **variable-length** hop is "however many edges it takes"
  — e.g. walking a `StyleGuide —[supersedes]→ StyleGuide` chain to find
  the *current* version from any historical one, which could be 1 hop or
  5 depending how many revisions have happened. That's where recursive
  CTEs get genuinely verbose (you're hand-rolling the recursion, its
  termination condition, and cycle protection yourself), and where
  Cypher's dedicated syntax — confirmed in AGE's own docs, e.g.
  `(u)-[:SUPERSEDES*1..5]->(v)` for "1 to 5 hops of this relationship
  type," or `(u)-[:SUPERSEDES*]->(v)` for "however many, no limit" — is a
  real, checked-against-AGE's-actual-docs win, not a hypothetical one.

### 3c. What AGE concretely unlocks (verified against AGE's own docs)

- **Variable-length path patterns**, confirmed in AGE's manual with
  working examples (`(u)-[:ACTED_IN*2]-(v)`, `(u)-[*3..5]->(v)`,
  `(u)-[*3..]->(v)`, `(u)-[*..5]->(v)`, unbounded `(u)-[*]->(v)`) — the
  single biggest concrete win over recursive CTEs, per §3b above.
- **`agtype`, a schema-flexible property type** on nodes/edges — adding a
  new property to a `StyleGuideRule` vertex (e.g. tagging some rules with
  a new `confidence` or `source_locale` attribute later) needs no
  migration, similar in spirit to a JSONB properties column on a plain
  table (which Option A can also use — this is a partial, not exclusive,
  AGE advantage).
- **One query language for pattern-matching, regardless of shape** —
  `MATCH`, `WITH`, `WHERE`, `ORDER BY`, `SKIP`/`LIMIT`, `MERGE`, `SET`/
  `REMOVE`, `UNWIND`, and aggregation functions are all confirmed
  supported by AGE's clause reference. Two clauses commonly relied on in
  other Cypher engines — `OPTIONAL MATCH` and multi-type alternation like
  `[:APPLIED_RULE|USED_TERM]` — are **not confirmed** in AGE's docs as
  fetched for this proposal; treat their availability as unverified until
  checked against the exact version pinned, not assumed.
- **Graph traversal and plain SQL can mix in one query/transaction** —
  because it's the same database, a query can `MATCH` over the graph to
  find relevant `StyleGuideRule` vertex ids, then join that result back
  against `quality_scores` or any other ordinary table, without crossing
  a database boundary. This is unique to the "graph inside Postgres"
  options (A or B) — Option 2 (Neo4j) can't do this at all, since the
  graph and the relational data live in different systems.
- **What it does *not* unlock:** community detection, PageRank, Leiden/
  Louvain clustering, or any other graph *algorithm* — AGE ships pattern
  matching and traversal, not algorithms. That ceiling is still §4 Option
  2 territory (a real graph-analytics engine) or pulling data out into a
  Python library (`networkx`/`igraph`) periodically — true whether the
  underlying storage is plain tables or AGE. AGE is not a stepping stone
  toward that capability; it's an ergonomics upgrade for pattern-matching
  and variable-length traversal, orthogonal to the community-detection
  question.

### 3d. Where plain tables are just as good

- The retrieval shape §4 Option 1 actually needs — "given a source text,
  pull relevant rules/terms within 1–2 hops of the vector-seeded
  candidates, optionally expand one more hop to sibling rules in the same
  guide section" — is **fixed-hop**, not variable-length. A couple of
  `JOIN`s handle it with no compromise relative to AGE.
- §7's clustering-based contradiction-detection technique (group units by
  existing `GlossaryTerm`/`StyleGuideRule` edges, compare within-cluster)
  is a `GROUP BY` over edge rows either way.
- Where the gap actually shows up: **variable-length chains** (the
  `supersedes` example in §3b) and **arbitrary, reviewer-driven
  exploration** ("show me everything within 4 hops of this unit, any
  relationship") — a real but narrow slice of the total feature set, and
  one that can be added later without disturbing anything built on plain
  tables first, since (per above) both live in the same database and can
  be queried together.

**Net:** nothing on the roadmap right now requires AGE's expressiveness;
its cost (≈2–3 days of one-time plumbing, a second query language living
alongside the ORM, no Alembic support) is paid up front regardless of
whether that expressiveness ever gets used. Plain tables cover the known
retrieval and consistency-checking patterns natively. AGE is confirmed
compatible and low-risk to add later — the recommendation is to defer it
until a specific traversal need (not a hypothetical one) shows up.

---

## 4. GraphRAG options

The actual ask: given an XLIFF file / document / page, build a retrieval
layer that surfaces the right style guide rules, glossary terms, brand
voice examples, and prior translations to the LLM doing localization —
and record what it retrieved as provenance.

### Option 1 — Postgres-native (pgvector + graph tables, same instance) — recommended

Everything lives in the Postgres database already in `docker-compose.yml`.

- `pgvector` columns on new `style_guide_chunks` / `glossary_terms` /
  `translation_exemplars` tables — nearest-neighbor retrieval for "what
  style/voice context is relevant to this source text."
- Graph tables (§3 Option A/B) hold structure: `Document → Page → Unit →
  Version → Agent`, plus new edges `Unit —[appliedRule]→ StyleGuideRule`,
  `Unit —[usedTerm]→ GlossaryTerm`.
- Retrieval = vector search seeds candidates, graph traversal expands them
  (e.g. "also pull every rule in the same style-guide section," "also pull
  this glossary term's `preferredOver` alternatives") — the graph-augmented
  RAG pattern, entirely in SQL/Cypher.
- **Retrieval itself becomes a PROV Activity** (`ContextRetrieval`,
  `used → StyleGuideRule/GlossaryTerm/exemplar entities`,
  `wasAssociatedWith → retrieval agent`), feeding the Translation activity
  the same way a source-text entity does today. This is the part that
  actually answers "why did the model pick this tone" later.

**Pros:** zero new services; retrieval and its provenance write land in the
*same transaction* as the translation — critical for a system whose whole
point is auditability (a cross-database RAG hop is exactly the kind of
untracked step that undermines the "what informed this translation"
story); reuses the pgvector image already running idle; fits the stated
"Postgres, not optional" design principle exactly.

**Cons:** no hierarchical community summarization (Microsoft GraphRAG's
signature "cluster the whole corpus into themed communities" step) —
weaker for "detect tone drift across an entire site/brand" analytics;
recursive-CTE/Cypher-in-Postgres traversal ceiling noted above.

### Option 2 — Dedicated GraphRAG engine, Postgres stays source of truth

Stand up Neo4j (or the Microsoft `graphrag` reference implementation, which
expects a graph + vector store pair) as a **derived, read-optimized**
index built from Postgres data — documents, units, style guides,
glossaries synced out on write or on a schedule. Gets real graph
algorithms (Leiden community detection, PageRank-weighted retrieval,
hierarchical community summaries) that a relational database can't do
well at scale.

**Pros:** purpose-built tooling, actively developed, the only option that
gets genuine "corpus-wide tone/style clustering" for free.

**Cons:** a second database to run, back up, and keep in sync
(eventually-consistent, not transactional — a translation could fire
before its retrieval context finishes syncing); every retrieval needs an
explicit write-back into Postgres to keep the PROV chain intact, which is
an integration seam rather than a side effect of the write path; a new
`docker-compose` profile for a project whose README currently sells "the
whole stack is self-contained."

### Option 3 — Embedded graph engine (Kuzu), no new server

Same idea as Option 2 but Kuzu runs in-process (file-based, like SQLite)
instead of as a network service — middle ground between Option 1's
operational simplicity and Option 2's query power.

**Cons:** still a second storage engine to keep consistent with Postgres
(dual-write, just without the network hop); community-detection-scale
GraphRAG features still weaker than a real Neo4j + `graphrag` stack;
younger/less proven than AGE, let alone Neo4j.

### Recommendation

**Option 1**, revisited toward Option 2 later *specifically* if/when
corpus-wide "tone drift across the whole site" analytics becomes a real
requirement (site-audit-style, akin to what `app/core/audit/` already does
for i18n compliance) rather than per-unit/per-document retrieval. Nothing
in Option 1's schema is wasted if that migration happens later — the graph
tables and PROV entities are the sync source either way.

---

## 5. New provenance surface: tone, style, voice

Independent of which GraphRAG option is chosen, this is the feature work
that actually answers the user's ask ("retain provenance and add features
for tone, adherence to style, voice"):

| New concept | Where it lives | Mirrors |
|---|---|---|
| `StyleGuideRow` (name, version, locale, voice description, tone attributes) | new table | `TranslationProjectRow` |
| `StyleGuideRuleRow` (rule_type: tone \| voice \| terminology \| formatting, rule_text, severity) | new table | — |
| `GlossaryTermRow` (source_term, target_term, locale, do_not_translate, notes) | new table | XLIFF `<glossary>` module already 📋 on the roadmap — this backs it |
| `StyleAdherenceScoreRow` (unit_id, style_guide_id, tone_score, voice_score, terminology_score, scorer, raw_response) | new table | `QualityScoreRow` exactly |
| `StyleAdherenceScorer` | `app/core/scoring/style_scorer.py` | `ClaudeQualityScorer` exactly — MQM-style but axes are tone/voice/register/terminology instead of accuracy |
| `ContextRetrieval` PROV Activity type + `StyleGuide`/`GlossaryTerm` PROV Entity types | `app/core/prov_builder.py` | Same shape as the existing `QualityAssessment` activity |
| `provx:styleAdherence`, `provx:styleGuideRef` notes | `app/xliff/xliff_service.py` | Same pattern as existing `provx:` notes |
| Style score as a second redrive threshold axis | `app/core/redrive/engine.py` | Already thresholds `quality_score`; add `style_score` alongside it, not a parallel engine |
| Style badge next to the existing quality badge | Review Shell `QualityBadge.tsx` | Same component, second metric |

The key design point: **retrieval provenance and style scoring are two
different things that both hang off the graph** — retrieval provenance
explains *what the model saw*; the style scorer explains *whether the
output was actually on-tone*. Both are worth having; the graph is what
makes the first one possible at all (today there's no record of "context"
beyond the source text itself).

---

## 6. Scope: XLIFF / document / page — one mechanism, three front doors

The user asked for this at "XLIFF file, build document, or page level."
Good news: those are already three ingestion paths onto the same
`TranslationUnit` (see `app/api/xliff_import.py`, `app/api/documents.py`,
`app/api/pages.py` / `page_fetch.py`) — a paragraph, a `<unit>`, and a
harvested DOM node all become the same row. Graph nodes and retrieval
context should attach at that shared `TranslationUnit`/`Document`/
`PageSnapshot` layer, so all three views get style/tone/voice tracking for
free rather than needing three separate implementations.

---

## 7. Supporting reference: Barry et al. 2025 (GenAIK)

[*GraphRAG: Leveraging Graph-Based Efficiency to Minimize Hallucinations in
LLM-Driven RAG for Finance Data*](https://aclanthology.org/2025.genaik-1.6/)
(Barry, Caillaut, Halftermeyer, Qader, Mouayad, Le Deit, Cariolaro,
Gesnouin — Workshop on Generative AI and Knowledge Graphs, Jan 2025)
targets a different domain (financial/regulatory document QA) but the
mechanism transfers directly to this proposal. Note: the ACL page and PDF
resisted full-text extraction (image-heavy PDF); the following is drawn
from the abstract/reported results, not the full methodology — treat the
specifics below as directionally useful rather than a verified reproduction.

Three things worth pulling in:

- **Fact-grounded retrieval over raw chunk retrieval ("FactRAG").** Instead
  of embedding whole style-guide/document passages and retrieving nearest
  chunks, extract structured facts (their paper: entity-relation triples
  from financial docs) into the knowledge graph and retrieve *those*. Here
  that means `StyleGuideRule` and `GlossaryTerm` should be first-class
  extracted rows (`rule_type`, `applies_to_locale`, `preferred_over`, ...),
  not just vector-searchable prose chunks — retrieval returns a small,
  structured, auditable fact ("use 'espace de travail' not 'workspace' in
  fr-FR marketing copy") instead of a paragraph the model has to
  re-interpret. This is also *why* it's cheap: their reported 80% token
  reduction comes from feeding facts instead of raw passages — directly
  relevant to controlling LLM cost when translating at document/site scale.
  **This saving is a data-modeling choice, not a graph-technology choice —
  it applies identically whether `StyleGuideRule`/`GlossaryTerm` rows live
  in plain Postgres tables or in AGE.** A `SELECT rule_text, target_term
  FROM style_guide_rules WHERE ...` returns the same compact, atomic fact
  as an equivalent Cypher `MATCH` — the token cost is set by *what* gets
  retrieved (one short structured row vs. a whole prose paragraph), not by
  which query language fetched it. §3a/§3c's AGE-vs-tables comparison is
  entirely about the *ergonomics of computing which facts are structurally
  relevant* (deeper/variable-length traversal); it has no bearing on how
  many tokens each retrieved fact costs once found. Put plainly: **you get
  this saving from extracting structured facts up front and only ever
  handing the model those facts instead of raw chunks — plain tables get
  you there just as well as AGE does, for the fixed-hop retrieval shape
  this system needs (§3d).**
- **Hybrid graph + vector retrieval ("HybridRAG").** Same shape as Option 1
  in §4 above — graph traversal for structural/relational context, vector
  search for fuzzy semantic matches, combined rather than either alone.
  Independent confirmation this is the right default, not a novel proposal
  of ours.
- **Sub-quadratic contradiction detection (O(k·n) vs O(n²)).** Their
  reported technique detects contradictions between regulatory documents
  without comparing every pair — implying a clustering step (grouping
  candidates into k groups, comparing within-cluster) rather than full
  pairwise comparison. This maps onto a concrete gap called out in §4's
  Option 1/2 tradeoff: **terminology and tone consistency checking across
  a whole document or site** (does this page's translation of "workspace"
  match every other page's? has tone drifted across a long document?)
  naively costs O(n²) unit-to-unit comparisons, which doesn't scale.
  Clustering units by `GlossaryTerm`/`StyleGuideRule` edges already in the
  graph (cheap, since those edges exist anyway) and comparing within each
  cluster gets the same O(k·n) shape — meaning Option 1 (Postgres-native,
  no community-detection engine) can likely cover a meaningful slice of
  what looked like an Option-2-only capability in §4, without standing up
  Neo4j. Worth prototyping before defaulting to Option 2 for that reason
  alone.

---

## 9. Persona validation: Product Marketing Manager, existing vendor/XLIFF-TMX workflow

Scenario used to stress-test §5–§7 against a real job, not just a
technical build: a PMM at a large org, writing copy for existing and new
products, sitting on a legacy XLIFF/TMX pipeline, routing work through
localization vendors (LSPs). Walking her actual job against what's
proposed surfaces both genuine wins and a few real gaps in scope so far.

### 9a. What already-proposed features give her, and why

| Her need | What serves it | Why it's faster / cheaper / higher quality |
|---|---|---|
| Don't restart brand knowledge from zero | `GlossaryTerm`/exemplar rows seeded from her *existing* TM, used as retrieval context (§4 Option 1) | AI-assisted first drafts are grounded in years of vendor-approved terminology, not generic MT — fewer redrive cycles, less vendor post-edit — **cheaper, higher quality** |
| Stop tone/terminology drift between vendors (or vendor vs. AI) | `StyleGuideRule`/`BrandVoiceProfile` as structured, versioned rules every translation is scored against (`StyleAdherenceScorer`, §5) | Drift becomes a measured score instead of a subjective complaint after the fact — **higher quality**, catchable pre-launch |
| Launch new products faster than a vendor round-trip allows | Style score as a second redrive threshold (§5) — off-brand output auto-flags/auto-redrives instead of waiting days for a vendor cycle, human-in-the-loop still gates what ships | **faster**, without giving up approval control |
| Prove *why* a translation says what it says (legal/brand review, or just her own "why does this say X" question) | `ContextRetrieval` PROV activity recording which rule/term/exemplar informed a choice (§5) | Most vendor-managed TMS tooling gives you a final string and maybe a TM-match %, not a reasoned trail — **higher quality of oversight**, not just of output |
| Review new marketing pages in context, not a spreadsheet of strings | Existing Review Shell overlay (`app/api/pages.py`, already built) | Not new work, but directly relevant — she reviews on the actual rendered page |
| Keep AI-driven changes from auto-publishing | Existing human-in-the-loop redrive gate (already built) | Control stays with her/regional marketing leads |

### 9b. Gaps this scenario surfaces — not yet in scope above

1. **TMX import.** The proposal (and the existing system) only imports/exports
   **XLIFF**. A PMM's "legacy file system" is just as likely raw **TMX**
   (Translation Memory eXchange, the older LISA/OSCAR vendor-exchange
   standard, distinct from XLIFF's `<matches>` module which is `📋` on
   `ROADMAP.md` but still XLIFF-flavored) — most enterprise LSPs still hand
   back `.tmx` alongside or instead of `.xliff`. Without a TMX import path,
   her years of vendor TM can't seed the graph at all, which guts §9a's
   first row. **New feature to add to scope:** `app/tm/tmx_import.py`
   parsing `<tu>`/`<tuv>` pairs into the same `TranslationUnitVersion` /
   exemplar rows XLIFF import already produces, tagging the source agent's
   `organization` field with the vendor's identity (that field already
   exists on `ProvenanceAgent`/`AgentRow` — just unused by any import path
   today).
2. **Vendor scorecard.** Once vendor identity rides on `organization`
   (via TMX import, or already for any vendor-delivered XLIFF), style/
   quality scores can be aggregated *by vendor* — "Vendor A: 92% style
   adherence, Vendor B: 74%." That's a genuinely different report from a
   per-unit score: it's the artifact a PMM actually uses in a vendor
   renegotiation or RFP, not just translation QA. **New feature:** a vendor/
   agent scorecard view + exportable report, reusing the branded-PDF
   pattern already built for site-audit reports (`app/core/audit/report.py`).
3. **Style/glossary brief export for vendor handoff.** She said she's
   *using* vendors, not necessarily replacing them with AI. The retrieved
   context (relevant `StyleGuideRule`s/`GlossaryTerm`s/exemplars, §4) has
   to be computed for AI translation anyway — serializing that same
   package into (or alongside) the XLIFF handoff so her *human* vendor
   linguists get identical grounding raises vendor output quality too, not
   just AI output. Without this, the whole style/voice investment only
   benefits the AI path, which doesn't match "I've been using vendors."
   **New feature:** attach retrieved `StyleGuideRule`/`GlossaryTerm` context
   to XLIFF exports as a human-readable brief, not just as `provx:` notes
   an LSP's tooling will likely ignore.
4. **Cross-page / cross-document tone & terminology consistency check.**
   §5's style scorer judges one unit at a time. A product launch spans many
   pages/emails/social posts/print — whether the *campaign* reads as one
   voice is a different question from any single segment's score, and is
   exactly the kind of check `app/core/audit/checks/` already does for
   i18n/compliance (mixed-locale, hreflang, ...) at the site level. **New
   feature:** a `tone_consistency`/`terminology_consistency` check added to
   the existing Site Audit tool, using §7's clustering technique (group by
   shared `GlossaryTerm`/`StyleGuideRule` edges, compare within-cluster) —
   infrastructure this proposal already needs for a different reason (§7),
   now with a second consumer.
5. **Source-language brand-voice check for authoring, not just translation
   QA.** She "creates new copy," not only oversees its translation. Nothing
   above touches source-language drafting. Since `StyleGuideRule`/
   `BrandVoiceProfile` and the scorer are locale-parameterized already,
   running the same scorer against her source-language draft *before*
   translation begins is a small extension with a real payoff: catching an
   off-brand English draft is cheaper than catching it after it's been
   translated into twelve languages. **New feature, smaller scope:** let
   `StyleAdherenceScorer` run source-side, not just target-side.
6. **Portable brand knowledge, framed explicitly as a business benefit, not
   just an engineering detail.** Enterprise LSP relationships often mean
   TM/glossary data is effectively vendor-locked — switching LSPs risks
   losing consistency built up over years. Because this system already
   treats Postgres as the system of record (not the vendor's TMS), items
   1–2 above mean her brand's linguistic assets live in *her* database,
   portable across whichever vendor or AI backend does the work next. Not
   new code, but worth stating plainly when this gets pitched internally.

### 9c. Net effect on scope

Items 1, 3, and 5 are natural additions to the Phase 13 build (they reuse
the same import/export/scoring machinery §5–§6 already call for, just
applied to one more format or one more direction). Items 2 and 4 lean on
Phase 13's data existing first (vendor-tagged scores, populated glossary/
style edges) and read more like a fast-follow Phase 14 — worth sequencing
that way rather than blocking Phase 13 on them.

---

## 10. Decisions — final

1. **Architecture direction** — Option 1 (Postgres-native), plain
   relational graph tables, no AGE for now (§3/§4).
2. **Sequencing** — style/tone scoring and GraphRAG retrieval build as one
   phase (Phase 13) rather than split, since the scorer's value depends on
   judging against *retrieved* context.
3. **TMX import (§9b.1)** — in scope for Phase 13 — without it, the graph
   has nothing of the user's own translation memory to retrieve from on
   day one.
4. **Vendor scorecard + cross-document consistency check (§9b.2, §9b.4)**
   — Phase 14, since both depend on Phase 13's data existing first.
5. **Further scenarios** — deferred until after Phase 13 and Phase 14 both
   ship, per the user.

Build tracking moves to `ROADMAP.md`'s Phase 13 / Phase 14 entries from
here.
