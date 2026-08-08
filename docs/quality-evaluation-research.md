# Translation Quality Evaluation — Standards Research

Status: ✅ Built as Phase 15 — see `ROADMAP.md`'s "MQM / COMET / METEOR
Quality Standards (Phase 15)" entry for what actually shipped
(`app/core/scoring/mqm_types.py`, the `hard_fail` redrive trigger,
`app/core/scoring/automatic/` for METEOR + COMET-Kiwi). This doc remains
the rationale/evaluation record — §8 was added after the initial pass,
verifying the MQM taxonomy against the MQM Council's own official
workbooks and resolving the COMET-Kiwi licensing question (no fee; the
constraint is the CC-BY-NC-SA license, accepted here under this project's
open-source/non-commercial framing).

Research memo comparing this codebase's two LLM-as-judge scorers
(`app/core/scoring/claude_scorer.py`, `app/core/scoring/style_scorer.py`) against
real industry standards (MQM, COMET, METEOR), and scoping what a non-LLM,
automatic-metric layer could realistically add.

Sources are cited inline. Where a source could not be reached or a claim could
not be verified, that is stated explicitly rather than inferred.

---

## 1. Executive Summary

**MQM.** The codebase's `ClaudeQualityScorer` is already MQM-*shaped* — it uses
the same three-tier severity vocabulary (critical/major/minor) and a penalty
formula structurally identical to MQM's "raw scoring model" — but it is a
single-dimension, fixed-weight simplification, not an MQM implementation. Real
MQM has **seven** top-level error dimensions (Terminology, Accuracy, Linguistic
Conventions, Style, Locale Conventions, Audience Appropriateness, Design &
Markup), each with named subtypes, and a scoring formula parameterized by an
evaluation word count, a reference word count, and per-error-type weights
(`themqm.org/mqm-pillars/the-mqm-scoring-models/`). The current scorer collapses
all seven dimensions into one undifferentiated error count and never
normalizes by text length. **Recommendation:** don't try to retrofit
`ClaudeQualityScorer` into full MQM — instead, reframe the existing
accuracy/style split as an intentional, minimal MQM-Core mapping: `QualityScorer`
already owns MQM's Accuracy dimension, and the Phase 13 `StyleAdherenceScorer`
already owns Style + a slice of Linguistic Conventions + Terminology. The
concrete, low-risk improvement is to make the Claude prompt return **typed
sub-errors per dimension** (not just a severity count) and normalize the score
by evaluation word count the way MQM's formula does, rather than a flat
0–100 subtraction. Full MQM (word-count normalization, calibration, ASTM
scorecards) is not worth building for an LLM-judge system whose real
bottleneck is prompt/rubric quality, not formula fidelity.

**COMET/METEOR.** These should become new, independent, **non-LLM** scorer
classes that sit alongside (not replace) `ClaudeQualityScorer` and
`ClaudeStyleScorer` in the same `app/core/scoring/` pattern — a third and
fourth entry in `CompositeScorer`'s "free/cheap checks before the model call"
philosophy, but the reverse: run *after* deterministic checks, as an optional
extra corroborating signal, not a scoring source of truth. **METEOR is
realistic to add now**: it's a pure-Python/NLTK computation, no GPU, no network
call, sub-millisecond per pair, and requires a reference translation — which
this system doesn't currently have as a first-class concept for most units
(source + AI-produced target, no independent human reference). METEOR is
therefore best scoped to **redrive-verification / regression-testing paths**
(comparing a new translation against a previously-approved human-reviewed
version used as a pseudo-reference), not the live translation API path.
**COMET is realistic only in QE/reference-free form (COMET-Kiwi), and only as
an optional, GPU-preferred, batch/offline scorer** — not on the live request
path. The practical blocker isn't just compute (CPU inference works, just
slower): it's licensing. The default reference-based checkpoint
(`Unbabel/wmt22-comet-da`) is Apache-2.0, but the reference-free QE checkpoint
this project would actually want (`Unbabel/wmt22-cometkiwi-da`) is
**CC-BY-NC-SA and gated behind a Hugging Face license click-through** — CC-BY-
NC-SA is a non-commercial license, which is a real constraint for a commercial
product and needs a legal decision before adoption, not just an engineering
one (`github.com/Unbabel/COMET/blob/master/LICENSE.models.md`). Given the
project runs on Mock/Claude/Ollama backends with no GPU infra assumed, COMET
should be documented as a **Phase 14+ "suggested, not yet built"** item behind
that licensing decision, while METEOR can be built now.

**MEDAL.** Could not verify any MT-quality-evaluation metric or framework
named MEDAL. A real, verifiable "MEDAL" does exist in Alon Lavie's recent
publication record, but it evaluates multilingual **open-domain dialogue**
(chatbots), not translation. Details and what was tried are in §5.

---

## 2. MQM — Multidimensional Quality Metrics

### 2.1 The standard

Source: `themqm.org` (fetched via browser after `WebFetch` returned HTTP 403 on
every `themqm.org` URL — the site appears to block the automated-fetch path;
pages rendered fine through an interactive browser, so the content below is
from primary-source pages, not search snippets).

- **Governance.** MQM is developed by an ASTM committee (WK46396); "MQM 2.0"
  was under active development as of the site's own FAQ (dated July 2021) with
  the error typology "mostly stable and widely implemented"
  (`themqm.org/about-us/`). It supersedes the older LISA QA Model and
  effectively subsumes TAUS DQF — "If you're using the TAUS DQF error
  typology, you are already using MQM 2.0" (same page). It is a free,
  published framework, not a paid/licensed product — the committee explicitly
  invites public feedback and participation.

- **Error typology.** Seven high-level error dimensions
  (`themqm.org/mqm-pillars/typology/`):
  1. **Terminology** — term doesn't match a required termbase/glossary, or isn't
     the domain-correct equivalent.
  2. **Accuracy** — target doesn't correspond to source propositional content
     (subtypes: Mistranslation, Overtranslation, Undertranslation, Addition,
     Omission, Do-not-translate, Untranslated).
  3. **Linguistic Conventions** (called "Fluency" in MQM 1.0) — grammar,
     punctuation, spelling, unintelligible/garbled text, character encoding,
     textual/discourse conventions.
  4. **Style** — grammatically fine but inappropriate: organization style
     guide violations, third-party style guide violations, register
     (formality) mismatch, awkward/unidiomatic/inconsistent style.
  5. **Locale Conventions** — number/currency/measurement/time/date/address/
     phone format, software shortcut-key conventions.
  6. **Audience Appropriateness** (called "Verity" in MQM 1.0) — culture-
     specific references the audience won't understand, offensive content.
  7. **Design and Markup** — layout, markup tag correctness, truncation/text
     expansion, missing text from layout, broken links.

  The full repository (**MQM-Full**) is large; **MQM-Core** is "a pre-established,
  widely used subset of error types at the two highest hierarchical levels...
  used as a default for maximum comparability"
  (`themqm.org/mqm-pillars/typology/`). Implementers are explicitly told to
  pick whatever granularity fits: "MQM is a modular system that allows you to
  use just a few categories or as many as you need... For many production
  environments, the top-level 'dimensions' may be sufficient"
  (`themqm.org/about-us/`).

- **Severity levels.** The standard's worked example uses **four** levels —
  neutral, minor, major, critical — pre-assigned penalty multipliers of
  **0, 1, 5, 25** respectively (`themqm.org/guidance/values-and-scores/`,
  `themqm.org/mqm-pillars/the-mqm-scoring-models/`). Definitions:
  - *Neutral* — a different solution is warranted but the translator shouldn't
    be penalized (e.g. bad termbase, preferential-only suggestion).
  - *Minor* — limited impact on accuracy/style/fluency/clarity; doesn't
    seriously impede usability or understandability.
  - *Major* — seriously affects understandability, reliability, or usability;
    significant loss/change of meaning, or occurs in a highly visible spot.
  - *Critical* — renders content unfit for purpose, or risks serious physical,
    financial, or reputational harm. **Any critical error count ≥ 1
    automatically triggers a Fail rating regardless of the numeric score.**

- **Scoring formula.** Per error type: `Error Type Penalty Total = ((minor_count
  × minor_multiplier) + (major_count × major_multiplier) + (critical_count ×
  critical_multiplier)) × Error_Type_Weight`. Sum across all error types =
  **Absolute Penalty Total (APT)**. Divide by the **Evaluation Word Count
  (EWC)** = **Per-Word Penalty Total**. Multiply by an arbitrary **Reference
  Word Count (RWC, typically 1000)** = **Normed Penalty Total** ("penalty
  points per thousand words"). The **raw Quality Score** = `(1 − Per-Word
  Penalty Total) × 100` (or equivalently, subtract the per-word penalty
  fraction from the Maximum Score Value of 100) — i.e. it expresses "the
  portion of the evaluated content that is correct"
  (`themqm.org/mqm-pillars/the-mqm-scoring-models/`,
  `themqm.org/guidance/values-and-scores/`). MQM also defines an optional
  **calibrated** score, which rescales the raw score around a pre-agreed
  Passing Threshold so differences near 100 are more legible to stakeholders
  — this is explicitly presented as an alternative, not a required step.

- **Practice / WMT.** MQM (and the related ESA — Error Span Annotation —
  protocol) is the standard human-evaluation methodology behind the WMT
  Metrics/Quality-Estimation shared tasks. In WMT25 ("Findings of the WMT25
  Shared Task on Automated Translation Evaluation Systems," Lavie et al.
  2025), most language pairs were judged with ESA, with Japanese→Chinese and
  English→Korean specifically annotated under the MQM protocol; participant
  metrics (including COMET variants) are scored by correlation against these
  human MQM/ESA judgments (`aclanthology.org/2025.wmt-1.24.pdf`,
  `www2.statmt.org/wmt24/metrics-task.html`). WMT24's metrics task similarly
  measured correlation with MQM scores at system- and segment-level.

- **MQM vs. automated metrics, per MQM's own FAQ:** "automated metrics
  typically provide just a number with no indication of how to improve
  outcomes... BLEU and METEOR scores also cannot provide actionable guidance...
  By contrast, MQM provides actionable guidance," while conceding MQM "does
  require more effort" and isn't usable "in production environments because
  they require human reference translations" — this line is actually about
  *automated* metrics, contrasting them with MQM's human annotation
  (`themqm.org/about-us/`).

### 2.2 Where this codebase's implementation diverges from real MQM

`app/core/scoring/claude_scorer.py` (read in full):

```python
score = max(0, 100 - 25 * critical - 10 * major - 3 * minor)
```

Comparing directly against the standard above:

| MQM concept | Real MQM | This codebase |
|---|---|---|
| Error dimensions | 7 (Terminology, Accuracy, Linguistic Conventions, Style, Locale, Audience Appropriateness, Design/Markup) | 1 implicit dimension — the prompt asks for "every translation error" undifferentiated by type; no `error_type` field at all, only severity |
| Subtypes | Dozens (Mistranslation, Omission, Addition, Untranslated, Wrong term, Register, etc.) | None — `ScoreError` (`app/core/scoring/base.py`) only carries `severity` + `count`, no category |
| Severity levels | 4: neutral / minor / major / critical | 3: critical / major / minor (no neutral) |
| Severity multipliers | 0 / 1 / 5 / 25 (from the standard's own worked example — MQM explicitly allows other schemes) | 3 / 10 / 25 — same critical value (25), but major and minor are both roughly 3–10x the MQM example's 1 and 5 |
| Normalization | By Evaluation Word Count, then by a 1000-word Reference Word Count | None — flat per-pair subtraction regardless of text length, so a 3-word UI label and a 300-word paragraph are penalized identically per error |
| Error Type Weights | Supported (e.g. weight Style errors higher for marketing copy) | Not present — no per-type weighting is possible since there are no types |
| Critical-error auto-fail | Any critical error ⇒ automatic Fail regardless of score | Not modeled — a single critical error only costs 25 points; three minor + one critical still nets a numeric score rather than a hard fail flag |
| Accuracy vs. Fluency/Style split | MQM keeps Accuracy as one of seven co-equal dimensions; Style and Linguistic Conventions are separate dimensions alongside it | This *does* map reasonably well: `ClaudeQualityScorer`/`QualityScorer` = Accuracy (+ implicitly some Linguistic Conventions, since "grammar/terminology/fluency" is folded into the same MAJOR bucket per the system prompt), and the Phase 13 `ClaudeStyleScorer`/`StyleScorer` = Style + Terminology + part of Audience/register. This is the one place the codebase's two-scorer architecture is already directionally aligned with MQM's dimension separation — see §2.3. |

Concretely, the system prompt in `claude_scorer.py` even blends dimensions
inside one severity bucket: "MAJOR - a clear grammar/terminology/fluency error"
merges what MQM treats as three separate dimensions (Linguistic Conventions,
Terminology, and part of Accuracy) into one severity tier. Real MQM would
never merge grammar and terminology errors into the same *type* — only
optionally into the same *severity*.

### 2.3 How the existing Accuracy/Style split maps to MQM today

This is a genuinely useful existing design decision worth calling out
explicitly in the report: `style_scorer.py`'s own docstring already states the
intent — "a translation can be word-for-word correct but off-brand, or
on-brand but wrong, and both get surfaced distinctly instead of one score
hiding the other." That is exactly MQM's philosophy of keeping Accuracy,
Style, and Linguistic Conventions as independent dimensions rather than one
blended score. Where it falls short of MQM is granularity *within* each
scorer, not the decision to split them.

- `QualityScorer`/`ClaudeQualityScorer` → best mapped to MQM's **Accuracy**
  dimension (Mistranslation/Omission/Addition/Untranslated), with some
  **Linguistic Conventions** bleed-in via its "MAJOR" grammar/fluency bucket.
- `StyleScorer`/`ClaudeStyleScorer` (Phase 13) → best mapped to MQM's
  **Style** + **Terminology** dimensions (its own three axes — tone, voice,
  terminology — line up almost one-to-one with MQM's Style/Register subtype
  and Terminology dimension), plus a slice of **Audience Appropriateness**
  when judging register.
- Neither scorer currently touches MQM's **Locale Conventions** or **Design
  and Markup** dimensions — but `app/core/scoring/deterministic.py` already
  covers a meaningful chunk of both for free: its structural checks
  (`html_tag_mismatch`, `number_mismatch`, `url_altered`, `email_altered`,
  `wrong_script`) are functionally Design/Markup and Locale-Convention checks,
  just not labeled as such. This is worth noting in the architecture section
  (§7) — the system already has de facto MQM Design/Markup and Locale
  coverage, it's just not named or reported that way.

### 2.4 Recommendation

Don't build full MQM (calibration, word-count normalization against an ASTM
scorecard, configurable Error Type Weights) — the added complexity buys
comparability across *external* MQM-using organizations, which isn't this
project's problem; its scorer output only has to be internally consistent for
the redrive-threshold decision it feeds. The concretely worth-doing, low-risk
changes are:

1. Add an `error_type` (or MQM dimension name) field to `ScoreError` so each
   flagged error names which of the (a small MQM-Core subset of) dimensions it
   belongs to — Accuracy/Mistranslation, Accuracy/Omission, Linguistic
   Conventions/Grammar, etc. This costs one more field in the Claude JSON
   response schema and turns today's opaque `critical: 2` into actionable,
   MQM-Core-labeled feedback, which is the exact gap MQM's own FAQ calls out
   in LLM/automated scores.
2. Adopt MQM's neutral severity level so evaluator disagreement / non-
   translator-fault issues don't silently inflate the major/minor counts.
3. Add a hard-fail flag mirroring MQM's "any critical error ⇒ automatic Fail"
   rule, decoupled from the numeric score — today a unit with one critical and
   zero other errors scores 75/100, which reads as "mostly fine" even though
   real MQM would flag it Fail outright.
4. Leave the flat (non-word-count-normalized) scoring as-is; this system
   scores individual short translation units, not multi-hundred-word
   documents, so MQM's per-1000-word normalization mostly doesn't apply at
   this granularity — normalizing per-unit by unit character/word length
   (not a fixed reference count) would be more useful than adopting MQM's
   literal RWC constant.

**Citations:** `https://themqm.org/mqm-pillars/typology/`,
`https://themqm.org/mqm-pillars/the-mqm-core-typology/`,
`https://themqm.org/guidance/values-and-scores/`,
`https://themqm.org/mqm-pillars/the-mqm-scoring-models/`,
`https://themqm.org/about-us/`,
`https://aclanthology.org/2025.wmt-1.24.pdf`,
`https://www2.statmt.org/wmt24/metrics-task.html`.

---

## 3. COMET

### 3.1 What it is

COMET (Crosslingual Optimized Metric for Evaluation of Translation) is
Unbabel/IST's neural, **trained** MT evaluation metric — a regression model
(built on XLM-R / InfoXLM) fine-tuned on human direct-assessment judgments,
as opposed to MQM (human rubric-based annotation) or METEOR (a fixed n-gram
matching formula, not learned). Source: `github.com/Unbabel/COMET` (root
`WebFetch` succeeded for this repo, unlike themqm.org).

- **Variants.**
  - *Reference-based*: default model `Unbabel/wmt22-comet-da`, trained on WMT17–
    WMT20 direct assessments — needs source, hypothesis, **and** a human
    reference translation.
  - *Reference-free / QE ("Quality Estimation")*: `Unbabel/wmt22-cometkiwi-da`
    (built on InfoXLM) — needs only source + hypothesis, no reference. Larger
    variants exist at 3.5B (`wmt23-cometkiwi-da-xl`) and 10.7B
    (`wmt23-cometkiwi-da-xxl`) parameters.
  - *Explainable (XCOMET)*: identifies actual **error spans** with **MQM-style
    severity labels** (minor/major/critical) — i.e. this variant already does
    something close to what §2.4's recommendation #1 asks for, natively.
  - `COMETINHO`/`eamt22-cometinho-da`: a distilled, much smaller/faster model
    ("the little metric that could" — also an Alon Lavie co-authored paper,
    see §6) explicitly built for lower-compute scenarios.

- **Install.** `pip install unbabel-comet` (PyPI package name is
  `unbabel-comet`, imported as `comet` in Python — current version 2.2.7 as of
  this research, Python ≥3.8, <4.0 — `pypi.org/project/unbabel-comet/`).

- **CLI.** `comet-score -s src.txt -t hyp.txt -r ref.txt` (reference-based);
  `comet-score --model Unbabel/wmt22-cometkiwi-da -s src.txt -t hyp.txt`
  (reference-free/QE, source+hypothesis only); `comet-compare` for paired
  statistical significance testing between two systems' outputs (paired t-test
  + bootstrap resampling).

- **Python API:**
  ```python
  from comet import download_model, load_from_checkpoint
  model_path = download_model("Unbabel/wmt22-comet-da")
  model = load_from_checkpoint(model_path)
  output = model.predict(data, batch_size=8, gpus=1)  # gpus=0 for CPU
  ```

- **Score scale.** Verified, not assumed: modern (2022+) checkpoints "scale
  scores between 0 and 1," where 1 = high quality, 0 ≈ random-level
  performance (`github.com/Unbabel/COMET` README). Older/pre-2022 checkpoints
  used unbounded z-score normalization with no fixed 0–1 range — so if this
  is ever adopted, pin to a `wmt22`+ checkpoint specifically for the bounded
  scale.

- **License — this is the material finding.** COMET model checkpoints do
  **not** all share one license
  (`github.com/Unbabel/COMET/blob/master/LICENSE.models.md`):
  - **Apache-2.0** (permissive, commercial-use-fine): `wmt20-comet-da`,
    `wmt20-comet-qe-da`, `eamt22-cometinho-da`, **`wmt22-comet-da`** (the
    reference-based default), `unite-mup`.
  - **CC-BY-NC-SA** (non-commercial, share-alike): `wmt22-unite-da`,
    **`wmt22-cometkiwi-da`** (the reference-free QE model — the one a live
    API without human references would actually need), `wmt23-cometkiwi-da-xl`,
    `wmt23-cometkiwi-da-xxl`, `unite-xl`, `unite-xxl`, `XCOMET-XL`,
    `XCOMET-XXL`.

  In practice, using `wmt22-cometkiwi-da` also requires logging into Hugging
  Face Hub and clicking through a gated-access license acknowledgment on the
  model page before `download_model()` will succeed
  (`huggingface.co/Unbabel/wmt22-cometkiwi-da`) — confirming the task's
  premise that Unbabel's models are gated in some cases. **CC-BY-NC-SA is a
  non-commercial license**; using it inside a commercial product's scoring
  pipeline is a legal question, not just an engineering one, and should be
  flagged to whoever owns licensing decisions before adoption, not decided
  by this research memo.

- **Compute.** GPU is supported via `--gpus`/`gpus=` but not required — `gpus=0`
  runs on CPU; the README notes CPU evaluation "is functional but
  significantly slower." For a live translation API request path (expecting
  low, predictable latency), CPU-only COMET inference on a transformer-scale
  model is not a good fit; it's much more appropriate for a **batch/offline
  redrive path** where seconds-per-unit latency is acceptable.

- **Mapping onto this system's 0–100 convention.** COMET's 0–1 scale multiplies
  cleanly onto `ScoreResult.score`'s existing `0.0–100.0` `Field(ge=0.0,
  le=100.0)` bound (`app/core/scoring/base.py`) — `comet_score * 100` — but
  the two numbers are **not semantically equivalent** and shouldn't be blended
  into the same field as the Claude MQM-style score. COMET's 0–1 is a learned
  regression against human *direct assessment* (holistic 0–100 slider
  judgments), not an MQM error-penalty subtraction; a COMET 0.85 and a
  Claude-scorer 85 are answering different questions even though they render
  the same. Keep them as a separate score column/axis, the same way Phase 13
  keeps style score independent from quality score (§7).

### 3.2 Recommendation

Feasible only as a new, optional, clearly-labeled **QE scorer class**
(`CometKiwiScorer` or similar) gated behind (a) a licensing decision on
CC-BY-NC-SA/commercial use, and (b) treating it as a batch/redrive-time
enrichment, never inline on the live translation-request path. Do not attempt
this with the reference-based (`wmt22-comet-da`) model in a live product flow
either, since it structurally requires a human reference translation this
system doesn't generally have at scoring time — reference-free (`cometkiwi`)
is the only variant that fits the shape of this problem at all, and that's
precisely the one with the NC license.

**Citations:** `https://github.com/Unbabel/COMET`,
`https://github.com/Unbabel/COMET/blob/master/LICENSE.models.md`,
`https://pypi.org/project/unbabel-comet/`,
`https://huggingface.co/Unbabel/wmt22-cometkiwi-da`.

---

## 4. METEOR

### 4.1 What it is

METEOR (Metric for Evaluation of Translation with Explicit ORdering) is a
lexical, **not learned**, MT evaluation metric. It aligns unigrams between a
hypothesis and a reference translation using a layered matching strategy
(exact surface form → stemmed form → WordNet-synonym form), then computes a
score from unigram precision, unigram recall, and a **fragmentation penalty**
that punishes matches that are scattered/out-of-order relative to the
reference (as opposed to contiguous, well-ordered chunks) — verified directly
from the original paper's own description (`aclanthology.org/W05-0909.pdf`,
also confirmed via the Google Scholar citation page for this exact paper).

### 4.2 Creator — verified

**Satanjeev Banerjee and Alon Lavie**, "METEOR: An Automatic Metric for MT
Evaluation with Improved Correlation with Human Judgments," ACL Workshop on
Intrinsic and Extrinsic Evaluation Measures for Machine Translation and/or
Summarization, Ann Arbor, Michigan, June 2005 — confirmed directly from
Google Scholar's citation record for this paper (11,478 citations at time of
research), which was one of the two specific citation pages the task asked to
be read and summarized:
`https://scholar.google.com/citations?view_op=view_citation&hl=en&user=iZEl7j4AAAAJ&citation_for_view=iZEl7j4AAAAJ:u5HHmVD_uO8C`.
Both authors were at the Language Technologies Institute, Carnegie Mellon
University. So yes — Alon Lavie is a co-creator, second author on the
foundational paper, correctly noted in the task brief. The metric was later
extended (paraphrase tables, phrase-level scoring, per-language tuning) by
Lavie with Michael Denkowski through ~2014 ("Meteor Universal: Language
Specific Translation Evaluation for Any Target Language," WMT 2014 — 2656
citations per the same Scholar profile), making METEOR a fairly continuously
maintained metric across nearly a decade of Lavie's CMU work.

### 4.3 Computing it in Python

`nltk.translate.meteor_score.meteor_score(references, hypothesis)` —
pre-tokenized reference(s) and hypothesis; configurable `preprocessing`
function (default `str.lower`), `stemmer` (default Porter stemmer), and
`wordnet` corpus reader for the synonym-matching stage
(`nltk.org/api/nltk.translate.meteor_score.html`,
`github.com/nltk/nltk/blob/develop/nltk/translate/meteor_score.py`). Needs
NLTK's `wordnet` corpus downloaded once (`nltk.download('wordnet')`) — a
one-time, small (~10s of MB), offline-after-download data file, not a live
network dependency at scoring time.

### 4.4 Lightweight enough to run inline — confirmed

Yes. No GPU, no large model weights, no external network call at score time
(only the one-time WordNet corpus download). It's a pure CPU string/lexical
computation, effectively free per call compared to an LLM round-trip. The
one real constraint, same as COMET's reference-based mode: **METEOR requires
a reference translation**, which is the metric's actual limiting factor for
this system, not compute.

### 4.5 Recommendation

METEOR is a good fit as a new `MeteorScorer` (non-LLM) class, but its
usefulness is bounded by reference availability, which this codebase mostly
doesn't have as a modeled concept today (per Read of `TranslationUnit` usage
across `claude_scorer.py`/`style_scorer.py` — units carry `source_text` +
`target_text`, no independent reference field). Two realistic entry points:
1. **Redrive regression checking** — when redriving a unit, score the new
   translation's METEOR against the *previous, already-approved* version as a
   pseudo-reference, to catch regressions cheaply before spending an LLM
   judge call.
2. **Golden-set / test-suite evaluation** — anywhere the project already has
   or will curate human reference translations (e.g. a evaluation harness or
   CI quality gate), METEOR is essentially free to compute alongside COMET
   and gives a second, uncorrelated (lexical vs. neural) signal.

It is not a good fit as a live per-request quality signal for ordinary
translation traffic, where no independent reference exists at all — that
role stays with the LLM judges and the deterministic checks.

**Citations:** `https://aclanthology.org/W05-0909.pdf`,
`https://www.cs.cmu.edu/~alavie/METEOR/`,
`https://scholar.google.com/citations?view_op=view_citation&hl=en&user=iZEl7j4AAAAJ&citation_for_view=iZEl7j4AAAAJ:u5HHmVD_uO8C`,
`https://www.nltk.org/api/nltk.translate.meteor_score.html`.

---

## 5. MEDAL — could not verify as an MT-evaluation metric

Per the task's explicit instruction: this was investigated before writing
anything, and the result is a **negative/redirected finding**, reported
plainly rather than guessed at.

**What was tried:**
- Web search for `"MEDAL" machine translation evaluation metric` — returned
  no MT-specific MEDAL metric; only general MT-metric articles (BLEU, METEOR,
  TER) with no MEDAL mention.
- Web search for `"MEDAL" Alon Lavie translation quality` — surfaced Lavie's
  ACL Anthology/ResearchGate author pages, but the actual "MEDAL" hit was
  about **dialogue** evaluation, not translation.
- Web search for `"MEDAL" metric evaluation dialogue OR summarization OR NLG
  framework acronym` — no additional MT-evaluation MEDAL surfaced.
- Checked Alon Lavie's Google Scholar profile directly (the exact URL given in
  the task, sorted by publication date, expanded via "Show more" back through
  2009) and the specific citation-page URL
  (`...citation_for_view=iZEl7j4AAAAJ:DyXnQzXoVgIC`) the task named. **This
  confirmed a real paper**: John Mendonça, Alon Lavie, Isabel Trancoso,
  *"MEDAL: A Framework for Benchmarking LLMs as Multilingual Open-Domain
  Dialogue Evaluators,"* Findings of the Association for Computational
  Linguistics: EACL 2026, pp. 2069–2097 (also posted as arXiv:2505.22777,
  first submitted May 2025; GitHub: `github.com/johndmendonca/medal`).

**What MEDAL actually is (verified, primary source — the Scholar citation
page's own abstract):** an automated multi-agent framework that uses several
LLMs to generate multilingual user-chatbot dialogues, then uses a strong LLM
(GPT-4.1) to do multidimensional analysis of chatbot quality (empathy, common
sense, relevance, etc.), builds a meta-evaluation benchmark from that, and
uses it to test whether other LLMs are reliable **dialogue** evaluators.

**Conclusion:** MEDAL is real, verifiable, and recent (2025/2026), and Alon
Lavie is a co-author — but it is a **dialogue-system / chatbot evaluation**
framework, not a machine-translation-quality metric, and has no direct
technical relationship to COMET, METEOR, or MQM beyond sharing an author and
a general "LLM-as-judge reliability" research theme. There is no evidence of
a distinct MT-specific "MEDAL" metric anywhere in Lavie's bibliography or in
general search. If the term was encountered elsewhere (e.g. in a vendor
deck or another paper) it should be treated as **either a reference to this
dialogue-evaluation MEDAL, or unverified**, not folded into this project's
MT-metric plans.

**Citations:** `https://arxiv.org/abs/2505.22777`,
`https://github.com/johndmendonca/medal`,
`https://scholar.google.com/citations?view_op=view_citation&hl=en&user=iZEl7j4AAAAJ&sortby=pubdate&citation_for_view=iZEl7j4AAAAJ:DyXnQzXoVgIC`.

---

## 6. Alon Lavie, 2021–present — annotated bibliography

**Access method used:** Google Scholar profile
(`scholar.google.com/citations?hl=en&user=iZEl7j4AAAAJ&view_op=list_works&sortby=pubdate`)
rendered fully through an interactive browser session (`get_page_text`), not
`WebFetch` — Scholar's JS-heavy listing did not need to be worked around with
search-snippet reconstruction in this case; the full sorted-by-date list back
through 2009 was read directly, so everything below is from that primary
source unless flagged otherwise. The two specific citation URLs given in the
task were also opened individually and are cited per-entry below.

**Current affiliation (verified from the Scholar profile header itself, which
is more current than search-engine snippets describing his LinkedIn/CMU
pages):** *"Distinguished Career Professor, Carnegie Mellon University; AI
Strategic Advisor, Phrase."* This is a change worth flagging explicitly: a
`WebFetch` of his CMU homepage (`cs.cmu.edu/~alavie/`) and general web search
both describe him as VP of AI Research at Phrase (Aug 2023–) after VP of
Language Technologies at Unbabel (where he directed COMET's development)
after a stint at Amazon (2015–2019, MT R&D). The Scholar page's own
self-maintained header — the more current of the sources checked — lists his
Phrase role as **"AI Strategic Advisor"** rather than VP, and the CMU
role has him rejoining active (non-adjunct) faculty duty in July 2025 as
Distinguished Career Professor after roughly a decade of adjunct status
during his industry roles. Net read: **CMU/academia is his current primary
affiliation; Phrase is now an advisory relationship, not his day job.** This
is an inference from comparing two dated-differently sources (Scholar header
vs. general search), flagged as such rather than stated as fully certain.

### Directly relevant to MT quality evaluation / QE / MQM / COMET (2021–present)

- **"Findings of the WMT25 Shared Task on Automated Translation Evaluation
  Systems: Linguistic Diversity is Challenging and References Still Help"**
  — A. Lavie, G. Hanneman, S. Agrawal, D. Kanojia, C.K. Lo, V. Zouhar, F.
  Blain, et al., *Proceedings of the Tenth Conference on Machine Translation
  (WMT)*, 2025, pp. 436–483. Lavie as **lead/organizing author**. This is the
  successor task that unified the separate MT Metrics and Quality Estimation
  shared tasks; per WMT25's own task page, most language pairs used the ESA
  human-eval protocol, two pairs used MQM. *Reusable takeaway:* this paper is
  the current state-of-the-art benchmark for how reference-based vs.
  reference-free automatic metrics correlate with human judgment across
  language pairs — directly relevant evidence for whether a QE-only (no
  reference) approach is "good enough" for this project's live-scoring path,
  given the paper's own headline finding that references still measurably
  help.
- **"Are LLMs Breaking MT Metrics? Results of the WMT24 Metrics Shared Task"**
  — M. Freitag, N. Mathur, D. Deutsch, C.K. Lo, E. Avramidis, R. Rei, B.
  Thompson, et al. (Lavie co-author), *Proceedings of the Ninth Conference on
  Machine Translation*, 2024, pp. 47–81. *Reusable takeaway:* directly
  examines whether LLM-as-judge scoring (this project's core approach for both
  its scorers) is starting to outperform or distort trained metrics like
  COMET — relevant risk-assessment reading before leaning further into
  Claude-as-judge as the system's primary quality signal.
- **"Data-Driven Asian Adapted MQM Typology and Automation in Translation
  Quality Workflows"** — B. Silva, M. Buchicchio, D. van Stigt, C. Stewart,
  H. Moniz, A. Lavie, *Journal of Specialised Translation*, 2024, pp. 98–126.
  *Reusable takeaway:* this is the single most directly applicable paper
  found — it's about adapting/customizing the MQM typology for a specific
  production context and automating parts of that workflow, i.e. almost
  exactly this project's stated goal of formalizing an ad-hoc MQM-style
  scorer against the real standard. Worth requesting/reading in full (not
  accessible in this research pass — journal article, not open-access
  arXiv/ACL Anthology PDF, so full text was **not** retrieved, only the title/
  venue/co-author list from Scholar).
- **"Results of WMT23 Metrics Shared Task: Metrics Might Be Guilty but
  References Are Not Innocent"** — M. Freitag, N. Mathur, C. Lo, E.
  Avramidis, R. Rei, B. Thompson, T. Kocmi, et al. (Lavie co-author),
  *Proceedings of the Eighth Conference on Machine Translation*, 2023, pp.
  578–628. *Reusable takeaway:* investigates reference quality's effect on
  metric reliability — relevant if this project ever builds the "pseudo-
  reference from previously-approved translation" pattern suggested in §4.5,
  since bad references would undermine both METEOR and reference-based
  COMET the same way this paper documents.
- **"The Inside Story: Towards Better Understanding of Machine Translation
  Neural Evaluation Metrics"** — R. Rei, N.M. Guerreiro, M. Treviso, L.
  Coheur, A. Lavie, A.F.T. Martins, *ACL 2023*. *Reusable takeaway:*
  interpretability analysis of COMET-style neural metrics (what signal they
  actually key on) — useful background if COMET/COMET-Kiwi is ever adopted,
  for understanding failure modes rather than treating it as a black box.
- **"Quality Fit for Purpose: Building Business Critical Errors Test Suites"**
  — M. Cabeça, M. Buchicchio, M. Gonçalves, C. Maroti, J. Godinho, P. Coelho,
  et al. (Lavie co-author), *EAMT 2023*. *Reusable takeaway:* "business
  critical errors" as a curated test-suite concept — directly analogous to
  what this project's deterministic.py "HARD (0)" tier already does
  informally (untranslated/garbage/broken-placeholder detection); this paper
  is the more rigorous version of that idea and could inform expanding
  deterministic.py's test-suite coverage.
- **"COMET-22: Unbabel-IST 2022 Submission for the Metrics Shared Task"** —
  R. Rei, J.G.C. De Souza, D. Alves, C. Zerva, A.C. Farinha, T. Glushkova, et
  al. (Lavie co-author), *WMT 2022*, pp. 578–585 (499 citations). The paper
  behind the `wmt22-comet-da` checkpoint discussed in §3.
- **"CometKiwi: IST-Unbabel 2022 Submission for the Quality Estimation Shared
  Task"** — R. Rei, M. Treviso, N.M. Guerreiro, C. Zerva, A.C. Farinha, C.
  Maroti, et al. (Lavie co-author), *WMT 2022*, pp. 634–645 (356 citations).
  The paper behind `wmt22-cometkiwi-da` discussed in §3.
- **"Results of WMT22 Metrics Shared Task: Stop Using BLEU – Neural Metrics
  Are Better and More Robust"** — M. Freitag, R. Rei, N. Mathur, C. Lo, C.
  Stewart, E. Avramidis, T. Kocmi, et al. (Lavie co-author), *WMT 2022*, pp.
  46–68 (326 citations). *Reusable takeaway:* the title is itself the
  finding — direct evidence, from Lavie's own co-authored shared-task
  results, against ever prioritizing a BLEU-style metric for this project.
- **"Searching for COMETINHO: The Little Metric That Could"** — R. Rei, A.C.
  Farinha, J.G.C. de Souza, P.G. Ramos, A.F.T. Martins, L. Coheur, et al.
  (Lavie co-author), *EAMT 2022*, pp. 28. *Reusable takeaway:* a distilled,
  small/fast COMET variant explicitly built for cheaper inference — the most
  relevant COMET variant if compute constraints (§3, no GPU infra assumed)
  turn out to be a harder blocker than the CC-BY-NC-SA licensing question.
- **"Business Critical Errors: A Framework for Adaptive Quality Feedback"**
  — C. Stewart, M. Gonçalves, M. Buchicchio, A. Lavie, *AMTA 2022*.
  Companion/precursor to the 2023 "Quality Fit for Purpose" paper above.
- **"System and Method for Training Multilingual Machine Translation
  Evaluation Models"** — R. Rei, C. Stewart, A.C. Farinha, A. Lavie, US
  Patent App. 17/382,241, 2022. Unbabel's COMET-related patent filing —
  background/provenance context only, not directly reusable for this
  project's design.
- **"Are References Really Needed? Unbabel-IST 2021 Submission for the
  Metrics Shared Task"** — R. Rei, A.C. Farinha, C. Zerva, D. Van Stigt, C.
  Stewart, P. Ramos, et al. (Lavie co-author), *WMT 2021*, pp. 1030–1040.
  *Reusable takeaway:* this is literally the paper testing whether reference-
  free (QE) scoring is "good enough" — directly on-point for this project's
  central COMET-Kiwi-vs-COMET-reference-based tradeoff discussed in §3.
- **"Results of the WMT21 Metrics Shared Task: Evaluating Metrics with
  Expert-Based Human Evaluations on TED and News Domain"** — M. Freitag, R.
  Rei, N. Mathur, C. Lo, C. Stewart, G. Foster, A. Lavie, O. Bojar, *WMT
  2021*, pp. 733–774.
- **"MT-Telescope: An Interactive Platform for Contrastive Evaluation of MT
  Systems"** — R. Rei, A.C. Farinha, C. Stewart, L. Coheur, A. Lavie, *ACL
  2021 (system demonstrations)*. *Reusable takeaway:* an open-source
  contrastive-evaluation UI/tool for comparing MT system outputs side by
  side with COMET scoring underneath — worth a direct look if this project
  ever builds an internal scorer-comparison or A/B evaluation dashboard,
  since it's an existing reference implementation of that exact idea from the
  same team.

### Adjacent but not MT-quality-specific (2021–present, noted for completeness)

Lavie's 2023–2026 output is heavily weighted toward **open-domain dialogue/
chatbot evaluation** with John Mendonça and Isabel Trancoso (a distinct
research thread, not MT-focused): *"MEDAL"* (2025/2026, §5), *"Soda-Eval"*
(EMNLP Findings 2024), *"ECoh: Turn-Level Coherence Evaluation for
Multilingual Dialogues"* (SIGdial 2024), *"On the Benchmarking of LLMs for
Open-Domain Dialogue Evaluation"* (NLP4ConvAI 2024), *"Simple LLM Prompting Is
State-of-the-Art for Robust and Multilingual Dialogue Evaluation"* (DSTC11,
2023), *"Towards Multilingual Automatic Open-Domain Dialogue Evaluation"*
(SIGdial 2023), *"QualityAdapt: An Automatic Dialogue Quality Estimation
Framework"* (SIGdial 2022). Also one philosophy paper, *"Towards a
Conversational Ethics of Large Language Models"* (H. Kempt, A. Lavie, S.K.
Nagel, *American Philosophical Quarterly*, 2024) — not technical, not
reusable for this project. And one very recent (2026) methods paper,
*"Dynamically Allocating Evaluation Effort for Model Ranking"* — V. Zouhar,
J. Kreutzer, A. Lavie, T. Kocmi, M. Post, O. Bojar, M. Sachan, arXiv preprint
2608.03437 — about efficient allocation of human-evaluation budget across
systems being ranked; potentially reusable if this project ever needs to
decide *which* units get the expensive LLM-judge treatment vs. cheaper
deterministic/METEOR checks under a fixed evaluation budget, but this was
only skimmed at the title/listing level, not read in full.

**Citations:** all entries above are drawn directly from
`https://scholar.google.com/citations?hl=en&user=iZEl7j4AAAAJ&view_op=list_works&sortby=pubdate`
(read in full via rendered browser, not snippet reconstruction) plus the two
task-specified citation pages:
`https://scholar.google.com/citations?view_op=view_citation&hl=en&user=iZEl7j4AAAAJ&sortby=pubdate&citation_for_view=iZEl7j4AAAAJ:DyXnQzXoVgIC`
(MEDAL) and
`https://scholar.google.com/citations?view_op=view_citation&hl=en&user=iZEl7j4AAAAJ&citation_for_view=iZEl7j4AAAAJ:u5HHmVD_uO8C`
(METEOR 2005). Abstracts beyond the two specifically-requested papers were
**not individually opened** for every 2021–2026 entry (over 30 papers) —
summaries above beyond MEDAL/METEOR are built from title, venue, co-author
list, and (for the shared-task papers) general knowledge of what WMT
Metrics/QE shared tasks report each year, not from reading each paper's full
abstract text. This should be treated as directionally reliable but not
independently abstract-verified per line item, except where marked
otherwise.

---

## 7. Proposed architecture sketch

Design-level only — no code. Follows the existing `app/core/scoring/`
conventions: an abstract base class per scoring family
(`base.py`/`style_base.py`), a factory with a settings-driven provider switch
(`factory.py`/`style_factory.py`), and a `Result` pydantic model per family
(`ScoreResult`/`StyleScoreResult`).

### 7.1 New scorer classes

- **`app/core/scoring/mqm_labels.py`** (or fold into `claude_scorer.py`) — not
  a new class, but the §2.4 change: extend `ScoreError` (currently
  `severity` + `count` only) with an optional `error_type` string constrained
  to an MQM-Core-subset enum (Accuracy/Mistranslation, Accuracy/Omission,
  Linguistic Conventions/Grammar, Terminology/WrongTerm, etc.), and extend
  `ClaudeQualityScorer`'s system prompt/JSON schema to return per-error
  `type` alongside severity. `ScoreResult`/`QualityScore` need no structural
  change — `errors: List[ScoreError]` already exists, this only enriches
  each entry.
- **`app/core/scoring/meteor_scorer.py`** — new `MeteorScorer(QualityScorer)`
  (or a distinct small ABC, e.g. `ReferenceScorer`, since it needs a third
  input — a reference text — that the existing `QualityScorer.score(unit)`
  signature doesn't carry). Pure-Python, NLTK-based, synchronous-fast enough
  that the existing `async def score` signature is a formality, not a real
  concurrency need.
- **`app/core/scoring/comet_scorer.py`** — new `CometKiwiScorer` implementing
  the same `QualityScorer` interface, wrapping `comet`'s `download_model` +
  `load_from_checkpoint` + `.predict()`, mapping the 0–1 output to 0–100 via
  `score * 100`. Needs its own settings flags (model checkpoint name, HF
  token, `gpus` count) and should lazy-import `comet`/`torch` the same way
  `claude_scorer.py` lazy-imports `anthropic` — so environments without the
  (large) COMET dependency installed don't break at import time.

### 7.2 Where they plug in

- **`CompositeScorer` (`factory.py`) stays the accuracy/QA path** exactly as
  today — `deterministic.py` free checks, then the configured LLM judge
  (`claude`/`ollama`). COMET/METEOR should **not** be inserted into
  `CompositeScorer`'s hot path; they're a different kind of signal
  (corroborating/automatic, not authoritative-for-redrive), and blending
  them into the same `score` field that drives `RedriveRun.threshold` would
  conflate three different scoring philosophies (deterministic floor / LLM
  MQM-style / neural-regression) into one number, the exact problem MQM's
  own multi-dimension design avoids.
- **New, parallel, optional axis** — same pattern Phase 13 already
  established for style: a `get_automatic_metric_scorer()`-style factory
  function (mirroring `get_style_scorer()`), a new
  `automatic_metric_scores` table (mirroring `style_adherence_scores`), and
  — if it's ever wired into redrive decisions at all — a third independent
  threshold axis on `RedriveRun`, e.g. `RedriveRun.comet_threshold` /
  `RedriveRun.meteor_threshold`, following exactly the precedent
  `RedriveRun.style_threshold` set in `alembic/versions/0018_redrive_style_
  threshold.py` and consumed in `RedriveEngine.preview()`/`.run()` via the
  `_below_threshold()` helper (`app/core/redrive/engine.py`). A unit would
  redrive if quality OR style OR (optionally) an automatic-metric axis falls
  below its own threshold — same "independent axis" pattern, not a blended
  composite score.
- **Given §3/§4's compute and reference-availability findings**, the
  *realistic* first cut is narrower than "wire into every redrive run":
  - METEOR: usable today wherever a prior approved version exists to serve as
    pseudo-reference — most naturally as an **optional pre-check inside
    `RedriveEngine`'s redrive step** (compare the new candidate translation's
    METEOR against the version being replaced, before spending an LLM judge
    call on it), not as a new top-level threshold axis initially.
  - COMET-Kiwi: gate behind the licensing decision (§3.2); if approved,
    scope to a **new offline/batch CLI or admin endpoint** ("score this
    redrive run's outputs with COMET-Kiwi for QA sampling") rather than any
    live-request or even live-redrive path, given CPU latency and GPU
    infra isn't assumed present.
- **Reporting surface:** Phase 13's PROV export pattern
  (`provx:styleAdherence` activity, `_style_brief_lines()` in
  `app/xliff/xliff_service.py`) is the right precedent to reuse — an
  automatic-metric axis would get its own `provx:automaticMetric` activity
  block (COMET score, METEOR score, model/checkpoint id as attributes) rather
  than being folded into the existing quality or style provenance notes.

### 7.3 What NOT to build

- No full MQM calibration/scorecard/ASTM-parameter machinery (§2.4) — not
  worth it for an internal, single-organization scoring pipeline.
  - No COMET reference-based scoring on any live path — it needs a human
  reference this system doesn't have at request time.
- No blending of COMET/METEOR scores into the existing `quality_score`
  0–100 field — keep them as clearly-labeled separate columns/axes so a
  consumer of the API always knows which scoring philosophy produced which
  number, the same transparency principle Phase 13 already applies to style
  vs. quality.

---

## 8. Follow-up verification (primary sources supplied directly by the user)

Everything in this section was checked against sources the initial research
pass didn't have — two official MQM Excel workbooks from `themqm.org`'s
downloads section, and a direct re-check of the COMET-Kiwi Hugging Face
model page — and materially sharpens §2 and §3 above.

### 8.1 COMET-Kiwi licensing — fee question resolved

Re-checked `https://huggingface.co/Unbabel/wmt22-cometkiwi-da` directly:
**there is no fee.** The "gate" is a free login + one-click acceptance of
the license terms, nothing more — no application review, no payment, no
paid tier. The blocker is purely legal, not financial: the license itself
is **CC-BY-NC-SA-4.0**, which prohibits commercial use regardless of
whether access costs money. No commercial-licensing contact is listed on
the model card. This doesn't change §3's recommendation, it just makes the
tradeoff concrete: adopting `wmt22-cometkiwi-da` costs nothing to access
but is a **licensing decision** (accept the NC restriction, e.g. scope
its use to internal/non-revenue-generating evaluation, or don't use it),
not a budget decision.

### 8.2 The official MQM-Core and MQM-Full typologies — now verified in full

The user supplied two official workbooks from themqm.org's own downloads
section (`themqm.org/resources/`), both stamped **"© 2024 MQM, content
created by The MQM Council... openly licensed via CC"** — confirming §2.1's
"free, published framework" finding, now from the primary spreadsheet
itself rather than the (403-blocked) website prose:

- **`2024_03-07-MQMFull_Master-Official.xlsx`** — the `MQMFull Master` sheet
  is the complete typology: **137 error types** across the 7 dimensions,
  each row carrying a Display Name, Description, real-world Examples,
  Discussion Notes, a hierarchy **Level #** (0 = dimension, 1 = top-level
  error type, 2–3 = subtypes), an **Alphanumeric Error Type PID**
  (e.g. `MQMC_101000` for Mistranslation), a **Mnemonic Error Type ID**
  (e.g. `mistranslation`), and an explicit **Parent** mnemonic
  (e.g. `accuracy`) — i.e. this is a ready-made, already-IDed taxonomy
  tree, not something that needs to be invented. The same workbook's
  `MQM-Core` sheet is the pre-curated, official **39-item** subset (Level
  0+1, occasionally one Level-2 item where the standard treats it as
  load-bearing) — this is the concrete, bounded list §2.4's
  recommendation #1 (add a typed `error_type` field) should actually be
  built from, rather than a subset invented for this project. Both
  taxonomies are consistent with §2.1/§2.2's dimension list (Terminology,
  Accuracy, Linguistic Conventions, Style, Locale Conventions, Audience
  Appropriateness [labeled "Verity" in the mnemonic column, confirming the
  MQM-1.0-name note in §2.1], Design and Markup).

- **`MQM-2.0-Dual-Scorecard-2025-05-09.xlsx`** — a filled-in worked example
  (En→Ar) of the actual scorecard, which makes §2.1's prose formula fully
  concrete and resolves the one part of it the web pages left implicit —
  **how the optional Calibrated Quality Score is actually computed.**
  From the live example (Passing Threshold Calibrated QS = 90, Acceptable
  Penalty Points/RWC = 10, Normed Penalty Total = 8 → Calibrated QS = 92):

  ```
  Raw Quality Score (RQS)   = MSV × (1 − Per-Word Penalty Total)
                              = 100 × (1 − 0.008) = 99.2

  Calibrated Quality Score  = 100 − (NPT ÷ AcceptablePenaltyPointsPerRWC)
                                    × (100 − PassingThresholdCalibratedQS)
                              = 100 − (8 ÷ 10) × (100 − 90) = 92
  ```

  i.e. calibration rescales the raw score around wherever the organization
  sets its Passing Threshold, so a score sitting exactly at the acceptable
  penalty ceiling lands exactly at the passing threshold, not at some
  arbitrary point — confirming §2.1's characterization ("stakeholders find
  differences near 100 more legible") with the actual arithmetic behind
  it. The sheet also confirms severity multipliers **0/1/5/25** for
  neutral/minor/major/critical are used as literal defaults in practice,
  not just a textbook example, and that Quality Rating is a simple
  threshold pass/fail flag alongside the numeric score (Raw QS 99.2 ≥
  Passing Threshold Raw QS 99 → "Pass").

### 8.3 Revised recommendation for §2.4 point 1

With the real MQM-Core taxonomy in hand, the earlier recommendation
("add an `error_type` field... constrained to an MQM-Core subset enum") is
now fully specified rather than aspirational: build a Python enum with
**39 members** (one per MQM-Core row), grouped under the 7 dimensions,
using the workbook's own mnemonic IDs as the enum values (`mistranslation`,
`term-inconsistency`, `wrong-term`, `grammar`, `register`, `awkward`,
`untranslated`, `truncation-text-expansion`, etc.) so the taxonomy stays
traceable back to the official PID/mnemonic scheme rather than inventing
new names. This is now a bounded, well-defined, roughly one-sitting
implementation task, not an open design question.

---

## Appendix: Access limitations encountered

- `themqm.org` returned **HTTP 403 Forbidden** to `WebFetch` on every URL
  tried (root page and every sub-page) — the site appears to actively block
  the automated-fetch tool's request signature/UA. Worked around by loading
  the same pages in an interactive browser session (`claude-in-chrome`) and
  extracting rendered text directly — all MQM content in §2 is from that
  primary source, not from search-engine snippets, so this is **not** a
  case of unverifiable/inferred content, just a different retrieval path
  than `WebFetch`.
- Google Scholar's author-works page (`view_op=list_works`) **did** fully
  render via the same interactive-browser path, including after clicking
  "Show more" to page back to 2009 — no search-fallback reconstruction was
  needed for the bibliography in §6.
- The "Data-Driven Asian Adapted MQM Typology" journal article (§6) was
  **not** read in full — it's a journal-hosted piece, not on arXiv/ACL
  Anthology, and full text wasn't retrieved in this pass; only its
  title/venue/co-authors are reported, and it's flagged as worth a follow-up
  read given how directly on-topic it is.
- Individual full abstracts were not pulled for every 2021–2026 paper listed
  in §6 (30+ items) — see the caveat at the end of §6.

---

## 9. Follow-up: broader Unbabel model collection review

Scope of this section: a targeted follow-up asking whether Unbabel's *full*
Hugging Face catalog (not just the two checkpoints already discussed in §3)
contains something better-suited than `wmt22-cometkiwi-da` for (1) scoring
LLM-produced translations specifically, and (2) evaluating "final content"
quality more broadly (tone/fluency/document-level), given the project's other
axis (`StyleAdherenceScorer`) already covers tone/voice via an LLM judge, not
a trained metric. Also resolves the §3.1 open question of whether a
reference-free "XCOMET-Kiwi" exists.

### 9.1 Method and what's actually in the catalog

`https://huggingface.co/collections/Unbabel/` does **not** 404 or redirect to
a 404 — it lands on a single named collection,
`https://huggingface.co/collections/Unbabel/tower-plus`, which is *not* a
catalog of all Unbabel collections, just one collection (Tower+ translation-
generation model weights and the IF-MT evaluation datasets). It does not
surface COMET/XCOMET/CometKiwi at all. The task's fallback path — browsing
Unbabel's full models list — was the one that actually worked:
`https://huggingface.co/Unbabel` plus a direct query of the Hugging Face
models API (`https://huggingface.co/api/models?author=Unbabel&limit=100`),
which is a more complete and structured source than the rendered models tab
(the org page reports "44 models" but the rendered tab under-lists them; the
API call returned all of them with `pipeline_tag`/`tags`/license metadata
attached). Every model ID and license claim below was checked against either
the model's own rendered Hugging Face card or this API response — not
inferred from the model name.

The 44-model catalog sorts into four groups relevant to this task, plus a
fifth group of unrelated internal/experimental checkpoints:

1. **Reference-free QE (CometKiwi family)** — `wmt22-cometkiwi-da` (already
   covered in §3), `wmt23-cometkiwi-da-xl`, `wmt23-cometkiwi-da-xxl`,
   `WMT24-QE-task2-baseline`, plus `-marian` re-exports of several of these
   (CTranslate2/Marian runtime format — same underlying model and license,
   not a distinct quality tier, not investigated further).
2. **Reference-based, error-span ("XCOMET")** — `XCOMET-XL`, `XCOMET-XXL`.
   This is the "explicitly branded XCOMET" the task and §3.1 asked about.
3. **LLM-judge model ("M-Prometheus")** — `M-Prometheus-3B`,
   `M-Prometheus-7B`, `M-Prometheus-14B`.
4. **Translation-generation models (not evaluators)** — `Tower-Plus-2B/9B/
   72B`, `TowerInstruct-*`, `TowerBase-*`. These *produce* translations,
   competing conceptually with this project's own Claude/Ollama translation
   backends, not with its scorers — out of scope for "quality scorer," noted
   only because the "Tower" branding could otherwise be mistaken for an
   evaluation tool.
5. **Not investigated further, checked at the title/tag level only and found
   irrelevant** — `XLM-R_L19_H12_FF3072`, `xlm-roberta-comet-small` (backbone/
   feature-extraction encoders used to build the above, not standalone
   scorers), `gec-t5_small` (English-only grammar error correction, not
   translation QE), `unite-mup`/`unite-xl`/`unite-xxl` (a different metric
   family, UniTE, already noted in §3.1's license table and not re-examined
   here since it wasn't part of either use case this follow-up was scoped
   to), and several clearly experimental/internal checkpoints
   (`test-model-whimsical-whisper`, `tiny-llama-3t-flavio-no-mt-but-parallel-
   annealed-SFT`, `mistral_7b_clip_sft_v0.1`, `lnext-qwen2p5-14b-siglip2-v5`)
   with no stated connection to translation quality evaluation.

### 9.2 Use case 1 — a better reference-free QE metric for LLM-produced translations

**`Unbabel/wmt23-cometkiwi-da-xl`** and **`Unbabel/wmt23-cometkiwi-da-xxl`**
are the direct successor-generation checkpoints. Verified from each model's
own Hugging Face card:

| | `wmt22-cometkiwi-da` (current) | `wmt23-cometkiwi-da-xl` | `wmt23-cometkiwi-da-xxl` |
|---|---|---|---|
| Backbone | InfoXLM | XLM-R **XL** | XLM-R **XXL** |
| Parameters | (not restated here, see §3) | ~3.5B | ~10.5–10.7B |
| Min. GPU memory stated on card | not stated | 15GB | 44GB |
| Reference-free | Yes | Yes | Yes |
| License | CC-BY-NC-SA-4.0 | CC-BY-NC-SA-4.0 | CC-BY-NC-SA-4.0 |
| Gated | Yes | Yes | Yes |
| Languages | multilingual | multilingual | 94 languages (card states results are "unreliable" for unsupported pairs) |

**`Unbabel/WMT24-QE-task2-baseline`** is also reference-free (source +
hypothesis only, InfoXLM backbone, "100+ languages" per its card) but is a
narrower artifact: it's a *baseline model for a shared-task track* (WMT24 QE
Task 2, the word-level quality-estimation subtask), built on the 2022
CometKiwi approach, and its output is a scalar score **plus binary word-level
OK/BAD tags** — not full MQM-style error spans with severity, just a
per-token flag. Same license (CC-BY-NC-SA-4.0) and same gating as the rest of
this family. Being an explicitly-named "baseline" (not a flagship numbered
release like the `wmt2X-cometkiwi-da` line) is itself a signal to treat it as
lower-maturity, not a production-grade upgrade path.

**What none of these model cards say, checked directly and not found:** no
card for `wmt23-cometkiwi-da-xl`, `wmt23-cometkiwi-da-xxl`, or
`WMT24-QE-task2-baseline` states that the model was specifically tuned on or
validated against **LLM-generated** translation output, as distinct from
traditional NMT system output. All three describe themselves purely in terms
of the WMT shared-task lineage (bigger backbone, later year) rather than a
target-model-type claim. This is a genuine gap in what Unbabel documents, not
something this research pass is inferring past. The closest primary-source
material on the LLM-vs-NMT question is still the paper already catalogued in
§6 — "Are LLMs Breaking MT Metrics? Results of the WMT24 Metrics Shared Task"
(Freitag, Mathur, Deutsch, Lo, Avramidis, Rei, Thompson, et al., including
Lavie, WMT 2024) — which is about metric robustness against LLM-produced
translations *in general*, not a claim about any specific Unbabel checkpoint
having been tuned for that scenario. No model card cross-references that
paper or claims to incorporate its findings.

**Recommendation for use case 1: do not switch.** The wmt23-xl/xxl models are
larger versions of the *same* architecture family, license, and gating as
`wmt22-cometkiwi-da` — not a documented LLM-specific improvement — while
requiring a **15GB (xl) to 44GB (xxl) minimum GPU**, which pushes even
further past this project's already-stated "no GPU infra assumed" position
(§3.1) than the base `wmt22-cometkiwi-da` checkpoint already does. Given the
project has no verified benchmark showing the accuracy gain is worth that
compute jump (and no card claims an LLM-specific gain to justify it either),
this is a strictly worse fit for a batch/offline scorer running without
dedicated GPU infra. `WMT24-QE-task2-baseline`'s only structural advantage —
reference-free — is already shared by `wmt22-cometkiwi-da`; its word-level
tags are a coarser signal than what the project would gain from XCOMET (see
§9.3), and its shared-task-baseline status makes it a worse choice than a
numbered flagship release for anything beyond experimentation.

### 9.3 Use case 2 — a "final content" / broader quality metric, and the XCOMET question

**XCOMET, resolved.** Exact model IDs: **`Unbabel/XCOMET-XL`** and
**`Unbabel/XCOMET-XXL`** (no separate "XCOMET" umbrella repo — these two
checkpoints are the entirety of the branded XCOMET line in Unbabel's HF
catalog).

- **What it does differently, confirmed from the primary paper** (Guerreiro,
  Rei, et al., "xCOMET: Transparent Machine Translation Evaluation through
  Fine-grained Error Detection," TACL 2024 / arXiv:2310.10482 — abstract read
  directly): "xCOMET integrates both sentence-level evaluation and error span
  detection capabilities... it does so while highlighting and categorizing
  error spans, thus enriching the quality assessment," and the model "is
  largely capable of identifying localized **critical** errors and
  hallucinations." This confirms the core capability §3.1 flagged as
  promising — error spans plus categorization, not just one scalar — and
  confirms at least a "critical" severity tier exists in its output
  vocabulary. It was **not possible to confirm from the sources reachable in
  this pass** whether XCOMET's error spans use the *full* MQM three-tier
  vocabulary (minor/major/critical) at the JSON output-schema level — the
  model card documents a `--to_json` export flag and a
  `model_output.metadata.error_spans` field, but a sample JSON output
  showing the actual field names/values inside those spans was not
  obtained. Flagged as unverified at that level of detail rather than
  assumed.
- **License:** **CC-BY-NC-SA-4.0** for both `XCOMET-XL` and `XCOMET-XXL` —
  the same restrictive non-commercial license as `wmt22-cometkiwi-da`. This
  does not change the §3/§8.1 licensing calculus at all.
- **New finding this pass surfaced that §8.1 didn't have:** both XCOMET
  cards contain a sentence `wmt22-cometkiwi-da`'s card does not — "For
  inquiries regarding commercial use authorization or any other questions,
  please contact us at ai-research@unbabel.com." This sentence was searched
  for specifically on `wmt22-cometkiwi-da`'s own card (re-checked directly
  in this pass) and was **not found there**. This is worth passing to
  whoever owns the licensing decision: a named commercial-authorization
  contact does exist for at least the XCOMET checkpoints, which suggests
  asking Unbabel directly may be a live option rather than a dead end — but
  this research pass did not contact Unbabel or test that path, so treat it
  as "a contact exists," not "commercial use was confirmed obtainable."
- **Gated:** Yes, both, via the same Hugging Face click-through
  license-acceptance pattern as `wmt22-cometkiwi-da`.
- **Parameters:** `XCOMET-XL` ~3.5B, `XCOMET-XXL` ~10.7B (per each model's
  own card) — the same two size points as the `wmt23-cometkiwi-da-xl/xxl` QE
  models in §9.2, suggesting a shared backbone-size lineage across both
  product lines.
- **Reference requirement — the decisive finding for this project:**
  **reference-based only.** Confirmed two ways: (1) the only Python usage
  example on either model's card passes `src`, `mt`, **and** `ref` — no
  example anywhere on either card omits the reference; (2) each card's own
  "need reference-free instead?" pointer directs users elsewhere, to
  `Unbabel/wmt22-cometkiwi-da` — which only makes sense as guidance if
  XCOMET itself isn't usable without a reference. A targeted Hugging Face
  model search for `"xcomet"` (76 results at time of research) surfaced only
  the two official Unbabel checkpoints plus third-party LoRA/fine-tune
  derivatives that *use* XCOMET as a training signal for other projects
  (e.g. ALMA-13B variants) — **no model named "XCOMET-Kiwi" or any other
  reference-free XCOMET variant exists**, from Unbabel or anyone else, as of
  this research date. This directly resolves §3.1's uncertainty: there is no
  reference-free XCOMET today.

  Because this project structurally has no reference translation available
  at scoring time (§3.2, §4.5), XCOMET's genuine capability upgrade (error
  spans + categorization over a single scalar) is gated behind exactly the
  one input this project doesn't have — the same disqualifying reason §3.2
  already ruled out the reference-based `wmt22-comet-da`. The upgrade is
  real; it just isn't reachable from this project's actual data shape.

**M-Prometheus, the other "final content" candidate.** Exact model IDs:
`Unbabel/M-Prometheus-3B`, `Unbabel/M-Prometheus-7B`,
`Unbabel/M-Prometheus-14B`. Paper: "M-Prometheus: A Suite of Open
Multilingual LLM Judges" (Pombal, Yoon, Fernandes, Wu, Kim, Rei, Neubig,
Martins; arXiv:2504.04953, Apr 2025) — abstract read directly. This is
architecturally different from every other model in this section: it is
**not** a trained regression/scalar metric like COMET/XCOMET, it's a
fine-tuned **LLM** (Qwen2.5 backbone at 3B/7B/14B) that acts as a judge,
producing "both direct assessment and pairwise comparison feedback on
multilingual outputs" — i.e. conceptually much closer to this project's
existing `ClaudeQualityScorer`/`StyleAdherenceScorer` pattern (LLM-as-judge)
than to a trained COMET-style head. Per the paper's own abstract, it targets
general **multilingual reward-benchmark** quality (20+ languages) as well as
"literary machine translation (MT) evaluation" specifically — i.e., unlike
COMET/XCOMET/CometKiwi, it is *not* scoped only to segment-level translation
accuracy, making it the one model in Unbabel's catalog that plausibly speaks
to "final content quality more broadly" the way the task asked.

- **License:** listed on the Hugging Face card as **"other"** for all three
  sizes. The actual license text/terms were **not retrievable** in this
  pass — the rendered card doesn't spell it out in the content this
  research could access, and the raw model-repo files return HTTP 401
  without an authenticated Hugging Face session even though the model
  itself is marked not-gated. This must be treated as **unverified**, not
  "presumably permissive" — do not assume anything about commercial-use
  rights for M-Prometheus without pulling the actual LICENSE file under an
  authenticated session first.
- **Gated:** No — publicly accessible without a license click-through
  (confirmed via the Hugging Face API response), unlike every COMET/XCOMET/
  CometKiwi checkpoint discussed in this document.
- **Parameters:** ~3B / ~8B / ~15B respectively (BF16 weights; the "14B" in
  the largest model's name refers to its Qwen2.5-14B-Instruct base).
- **Reference-free vs. reference-based:** could not be cleanly confirmed
  either way. The one usage example visible on the `M-Prometheus-3B`/`-14B`
  cards is a **direct-assessment** prompt that includes "a reference answer
  that gets a score of 5" — i.e. reference-based as demonstrated. The
  paper's broader claim of evaluating general "multilingual reward
  benchmarks" is suggestive of reference-free/preference-style use (that's
  the norm for reward-model benchmarks generically) but this was not
  independently confirmed against M-Prometheus's actual prompt templates
  beyond the one reference-based example each card shows. Flagged as
  unverified rather than assumed either way.
- **Relevance to this project, honestly assessed:** M-Prometheus overlaps
  functionally with scoring work this project has already built, rather than
  filling a gap. Adopting it would mean **replacing or supplementing
  Claude-as-judge with a smaller, self-hosted, open-weight judge model** — an
  infrastructure/self-hosting decision (running a 3B–14B LLM), not a "new
  capability this project currently lacks." Combined with the unverified
  "other" license, this is not a slam-dunk addition; it's a reasonable
  follow-up to revisit only if the project ever has a concrete reason to
  move a judging role off the Anthropic API (cost, latency, or data-
  residency reasons, none of which this research pass was asked to assess),
  not something to fold into the COMET/METEOR scorer plan in §7.

### 9.4 Recommendation

**Stick with `wmt22-cometkiwi-da` as currently integrated. Nothing found in
this broader catalog review is a clear enough win to justify switching or
adding an alternative right now**, for reasons specific to each use case:

1. **Use case 1 (LLM-produced translations):** `wmt23-cometkiwi-da-xl/xxl`
   are the same architecture/license/gating at larger scale, with no
   documented LLM-specific tuning or validation claim on either card, for a
   15GB–44GB minimum-GPU cost this project's stated infra posture (§3.1)
   can't presently absorb. `WMT24-QE-task2-baseline` is reference-free but a
   narrower shared-task baseline with coarser (binary word-level) output and
   no maturity signal beyond "baseline." None of the three changes the
   underlying answer to "is there something built and validated
   specifically for LLM output" — that remains unconfirmed anywhere in
   Unbabel's catalog.
2. **Use case 2 (broader final-content quality):** XCOMET-XL/XXL's error-
   span upgrade is real (confirmed from the primary paper) but is
   reference-based only, and no reference-free "XCOMET-Kiwi" exists — so it
   is disqualified by the same no-reference-at-scoring-time constraint that
   already ruled out `wmt22-comet-da` in §3.2, independent of licensing.
   M-Prometheus is a genuinely different, broader-scope tool (an open-weight
   LLM judge, not a segment-level regression metric) but it duplicates
   functionality this project already has via `ClaudeQualityScorer`/
   `StyleAdherenceScorer`, carries an unverified "other" license, and would
   require self-hosting a 3B–14B model — a materially bigger decision than
   this research memo should resolve on its own.
3. **Licensing pattern, catalog-wide:** CC-BY-NC-SA-4.0 + gated is the norm
   across nearly every scoring-oriented Unbabel checkpoint this pass
   touched — `wmt20`/`wmt22`/`wmt23` CometKiwi, both XCOMET sizes, UniTE, and
   `WMT24-QE-task2-baseline` all share it. The one Apache-2.0 exception
   found anywhere in this review is still the reference-based
   `wmt22-comet-da` already documented in §3.1, which doesn't fit this
   project's no-reference reality regardless of its friendlier license. Not
   one newer/alternative checkpoint examined in this follow-up carries a
   more permissive license than what's already been evaluated.
4. **One concrete, actionable, not-yet-acted-on lead for whoever owns the
   licensing decision:** XCOMET's model cards list
   `ai-research@unbabel.com` as a commercial-use-authorization contact;
   `wmt22-cometkiwi-da`'s card does not show that sentence. If the CC-BY-
   NC-SA restriction on `wmt22-cometkiwi-da` ever becomes a blocker worth
   resolving rather than working around, emailing Unbabel directly (via the
   contact its own sibling checkpoints publish) is an untested but concrete
   next step — this research pass did not attempt that contact.

**What was not verified, stated plainly:**
- No independent benchmark numbers were pulled to confirm
  `wmt23-cometkiwi-da-xl/xxl` actually correlate better with human judgment
  than `wmt22-cometkiwi-da` — the recommendation above relies on the model
  cards' own framing (larger backbone) plus the compute/license/LLM-tuning
  factors, not a verified accuracy delta.
- XCOMET's exact error-span severity-label schema (minor/major/critical vs.
  something else, at the JSON field level) was not confirmed from a real
  sample output.
- M-Prometheus's actual "other" license terms were not retrieved — flagged
  as an open item, not assumed permissive or restrictive.
- Whether the underlying `comet` Python library supports an undocumented
  reference-free invocation of XCOMET (e.g. by passing an empty or
  duplicated `ref` field) was not tested — only what each model card
  explicitly documents was used to reach the reference-based conclusion in
  §9.3.

**Citations:** `https://huggingface.co/collections/Unbabel/tower-plus`,
`https://huggingface.co/Unbabel`,
`https://huggingface.co/api/models?author=Unbabel`,
`https://huggingface.co/Unbabel/wmt22-cometkiwi-da`,
`https://huggingface.co/Unbabel/wmt23-cometkiwi-da-xl`,
`https://huggingface.co/Unbabel/wmt23-cometkiwi-da-xxl`,
`https://huggingface.co/Unbabel/WMT24-QE-task2-baseline`,
`https://huggingface.co/Unbabel/XCOMET-XL`,
`https://huggingface.co/Unbabel/XCOMET-XXL`,
`https://arxiv.org/abs/2310.10482` (xCOMET paper),
`https://huggingface.co/Unbabel/M-Prometheus-3B`,
`https://huggingface.co/Unbabel/M-Prometheus-14B`,
`https://arxiv.org/abs/2504.04953` (M-Prometheus paper),
`https://huggingface.co/models?search=xcomet`.

---

## 10. Follow-up: Tower / Tower+ (translation + evaluation)

Scope of this section: the task's premise — that this codebase's Ollama QE
scorer (`app/core/scoring/ollama_scorer.py`, `OLLAMA_QE_MODEL` in
`app/core/config.py`) is a port of a TowerInstruct-based approach from the
user's other project ("peripateticware") — is confirmed directly from this
repo's own code comments: `ollama_scorer.py`'s module docstring literally
says "mirrors peripateticware's TowerInstruct-via-Ollama approach," and
`config.py`'s default `ollama_qe_model` is
`hf.co/s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF:Q4_K_M`. This section
investigates the full Tower family (including the newer **Tower+**
generation, not yet used anywhere in this codebase) as a candidate for
**both** a translation backend and an evaluation backend, per the task's
brief, alongside the planned multi-provider architecture (OpenAI, Ollama,
Claude, Gemini, Google Translate, MS Translator, LMStudio, vLLM).

### 10.1 The Tower model family — verified checkpoint-by-checkpoint

Every repo ID, parameter count, base model, and license below was read
directly from that checkpoint's own Hugging Face model card (`WebFetch`),
not inferred from the model name or from a sibling checkpoint's card — the
same discipline §3/§9 already applied to the COMET family, per the task's
explicit instruction not to assume license uniformity across a family.

**Generation 1 — TowerBase / TowerInstruct (Llama-2 and Mistral backbones):**

| Repo ID | Params | Base model | License |
|---|---|---|---|
| `Unbabel/TowerBase-7B-v0.1` | 7B | Llama 2 (continued pretraining) | CC-BY-NC-4.0 + Llama 2 Community License |
| `Unbabel/TowerBase-13B-v0.1` | 13B | Llama 2 (continued pretraining) | CC-BY-NC-4.0 + Llama 2 Community License |
| `Unbabel/TowerInstruct-7B-v0.1` | 7B | `TowerBase-7B-v0.1` | CC-BY-NC-4.0 + Llama 2 Community License |
| `Unbabel/TowerInstruct-13B-v0.1` | 13B | `TowerBase-13B-v0.1` | CC-BY-NC-4.0 + Llama 2 Community License |
| `Unbabel/TowerInstruct-7B-v0.2` | 7B | `TowerBase-7B-v0.1` | CC-BY-NC-4.0 + Llama 2 Community License |
| `Unbabel/TowerInstruct-Mistral-7B-v0.2` | 7B | Mistral (not Llama-2) | CC-BY-NC-4.0 |

`TowerInstruct-Mistral-7B-v0.2`'s own card states it reaches "performance
comparable to TowerInstruct-13B-v0.2, while being half the size" — implying
a `TowerInstruct-13B-v0.2` exists, but that specific card was not
independently fetched in this pass (only referenced by a sibling card), so
its exact license/size should be treated as **likely-but-unconfirmed**
rather than verified the way every other row in this table is.

**Generation 2 — Tower+ (multiple backbones, released June 2025):**

| Repo ID | Params (card's own figure) | Base model | License |
|---|---|---|---|
| `Unbabel/Tower-Plus-2B` | 2B (card also says "3B total") | Gemma 2 2B | **CC-BY-NC-SA-4.0** |
| `Unbabel/Tower-Plus-9B` | 9B | Gemma 2 9B | **CC-BY-NC-SA-4.0** |
| `Unbabel/Tower-Plus-72B` | 73B | Qwen 2.5 72B | **CC-BY-NC-SA-4.0** |

Collection page: `huggingface.co/collections/Unbabel/tower-plus`. Paper:
"Tower+: Bridging Generality and Translation Specialization in Multilingual
LLMs" (arXiv:2506.17080, June 2025) — abstract and HTML full text both
read directly.

**License finding — the material one, mirroring §3's COMET finding:**
Tower's license is **not uniform across generations**, the same kind of
non-uniformity the COMET research found across checkpoints. Generation 1
(TowerBase/TowerInstruct) is **CC-BY-NC-4.0** (non-commercial, no
share-alike clause); Tower+ is **CC-BY-NC-SA-4.0** (non-commercial **and**
share-alike — derivatives/fine-tunes of Tower+ must themselves be
distributed under the same license terms). Both are non-commercial, so the
practical "can this ship in a commercial product" answer is the same "no
without a separate arrangement" as COMET-Kiwi (§3.1/§8.1) — but the added
share-alike clause on Tower+ is a strictly stronger restriction than
Generation 1 carries, worth flagging to whoever owns the licensing decision
if this project ever wants to fine-tune or redistribute a modified Tower+
checkpoint (not just call it for inference), since CC-BY-NC-SA would compel
that derivative to also be CC-BY-NC-SA.

**A community-GGUF licensing wrinkle, found and worth flagging explicitly:**
the exact GGUF repo already configured as this project's default
(`s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF`) displays its own Hugging Face
license tag as **"openrail,"** not CC-BY-NC-4.0. This is the re-uploader's
own (looser) tag, not a re-license granted by Unbabel — the underlying
weights are still governed by `Unbabel/TowerInstruct-7B-v0.1`'s actual
CC-BY-NC-4.0 + Llama 2 Community License terms regardless of what license
string a third-party GGUF mirror displays. This is a genuinely useful
finding for whoever owns the licensing decision: **don't take a community
GGUF repo's license tag at face value** — trace it back to the original
Unbabel checkpoint's own card, the same way §8.1/§9 did for COMET.

**Citations:** `https://huggingface.co/Unbabel/TowerBase-7B-v0.1`,
`https://huggingface.co/Unbabel/TowerBase-13B-v0.1`,
`https://huggingface.co/Unbabel/TowerInstruct-7B-v0.1`,
`https://huggingface.co/Unbabel/TowerInstruct-13B-v0.1`,
`https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2`,
`https://huggingface.co/Unbabel/TowerInstruct-Mistral-7B-v0.2`,
`https://huggingface.co/Unbabel/Tower-Plus-2B`,
`https://huggingface.co/Unbabel/Tower-Plus-9B`,
`https://huggingface.co/Unbabel/Tower-Plus-72B`,
`https://huggingface.co/collections/Unbabel/tower-plus`,
`https://arxiv.org/abs/2506.17080`,
`https://huggingface.co/s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF`.

### 10.2 The multi-task claim — verified, with an important caveat on exact schema

The task's premise ("Tower models do translation AND evaluation in one
model, unlike COMET") is **directionally correct and verifiable from
primary sources, but the exact output schema for the evaluation task could
not be confirmed to the level of detail this doc holds itself to
elsewhere** (e.g. §9.3's honest "XCOMET's exact error-span severity-label
schema... was not confirmed from a real sample output" caveat applies here
too, for the same reason: no raw example record was obtained).

**What is confirmed, from primary sources:**
- Every Generation-1 model card fetched (`TowerInstruct-7B-v0.1`, `-13B-v0.1`,
  `-7B-v0.2`) lists tasks including general MT, automatic post-editing,
  named-entity recognition, grammatical error correction, paraphrase
  generation — and `TowerInstruct-7B-v0.1`'s card additionally names
  **"Machine Translation Evaluation"** explicitly as one of the supported
  tasks. (`TowerInstruct-7B-v0.2`'s own intended-use paragraph, fetched
  separately, does **not** repeat that exact phrase in its task list — this
  is flagged as an inconsistency between card revisions, not a confirmed
  capability regression, since it wasn't tested empirically either way.)
- The training dataset behind this, `Unbabel/TowerBlocks-v0.2` (its own HF
  dataset card, fetched directly), confirms the "Machine Translation
  Evaluation" task's data sources by name: **"WMT20 to WMT22 Metrics
  MQM"** and **"WMT17 to WMT22 Metrics Direct Assessments."** This is a
  real, checkable claim, and it directly supports the task's "does it output
  MQM spans, a scalar score, or both" question: WMT Metrics **MQM** data is
  human error-span/severity annotation (the same MQM style this project's
  own `ClaudeQualityScorer` approximates), while WMT Metrics **Direct
  Assessment** data is a single 0–100 holistic scalar judgment (the same
  kind of data COMET's own `-da` checkpoints are trained on, per §3.1). So
  TowerBlocks trained Tower on **both** styles of evaluation output as
  separate examples of the same "evaluation" task type — meaning the model
  is plausibly capable of producing either an MQM-style critique or a
  scalar-style score depending on how it's prompted, consistent with the
  task's framing.
- The newer generation carries this forward by name: the Tower+ paper's own
  SFT task breakdown (read from the arXiv HTML full text) lists, under
  "post-translation" tasks, **"automatic post-editing, machine translation
  quality evaluation"** as part of the translation-related slice of its
  instruction-tuning mixture — so "evaluation" remains an explicitly named,
  trained task in Tower+, not something dropped between generations.

**What could not be confirmed, stated plainly:**
- Neither Unbabel's public `deep-spin/tower-eval` evaluation-harness repo
  (its example configs under `configs/tower_paper/` only define `mt`,
  `ape`, and `ner` task configs, scored by external metrics — chrF, BLEU,
  COMET, COMET-Kiwi — not a Tower-generates-a-judgment task) nor a direct
  query of the `TowerBlocks-v0.2` dataset's own row-level content (via the
  Hugging Face `datasets-server` API — the specific rows sampled in this
  pass happened to all be Spanish NER examples, not MT-evaluation examples)
  yielded an actual verbatim instruction/output pair for the "Machine
  Translation Evaluation" task. **This means the exact prompt template and
  exact output format (JSON? free-text with a score? free-text with error
  spans? does the instruction include a reference field or not?) for
  Tower's evaluation task specifically is not verified from a primary-source
  example in this research pass** — only that the *capability is trained
  and named*, per the model cards and dataset card above. Anyone
  implementing this should pull an actual `TowerBlocks` MT-evaluation
  example row (filterable via the dataset's task column) before writing a
  production prompt, rather than trusting a guessed template.
- Whether the WMT Metrics MQM/DA training examples were formatted
  **reference-based** (source + MT + human reference, which is how WMT
  Metrics MQM/DA annotation is typically collected) or **reference-free**
  (source + MT only) inside TowerBlocks was **not confirmed either way**.
  This matters a lot for this project specifically, given §3/§4's
  recurring finding that this system generally has no reference translation
  at scoring time — if Tower's evaluation task was trained reference-based,
  its real-world reference-free performance (the only mode this project can
  actually use it in) is unvalidated, exactly the same shape of caveat
  §3.2 already applies to `wmt22-comet-da`.

**Citations:** `https://huggingface.co/Unbabel/TowerInstruct-7B-v0.1`,
`https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2`,
`https://huggingface.co/datasets/Unbabel/TowerBlocks-v0.2`,
`https://arxiv.org/html/2506.17080v1`,
`https://github.com/deep-spin/tower-eval`,
`https://raw.githubusercontent.com/deep-spin/tower-eval/main/configs/tower_paper/tower_instruct_0_shot.yaml`.

### 10.3 How to run them — serving paths, and prompt templates

**Native / vLLM / transformers.** Every Tower checkpoint (Generation 1 and
Tower+) is a standard Hugging Face `transformers`-loadable causal LM — no
custom architecture. Tower+'s own model cards (`Tower-Plus-9B`,
`Tower-Plus-72B`, both fetched directly) explicitly state **"we recommend
using vLLM rather than Hugging Face [transformers]"** for serving — i.e.
Unbabel's own stated preferred production path for Tower+ specifically is
vLLM, not bare `transformers`, and not Ollama/llama.cpp. This is a
difference from how this project currently runs Generation-1 TowerInstruct
(Ollama/GGUF only, per `ollama_scorer.py`) worth being explicit about: the
GGUF/Ollama path works for Tower+ too (see below), it just isn't the path
Unbabel itself recommends first.

**GGUF quantizations — confirmed to exist, same community-conversion
pattern as the `s3nh` TowerInstruct-7B-v0.1 repo already in this project's
default config:**

| Model | GGUF repo(s) found | Q4_K_M size |
|---|---|---|
| `TowerInstruct-7B-v0.1` | `s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF` (already this project's default), `TheBloke/TowerInstruct-7B-v0.1-GGUF` | 4.08 GB |
| `TowerInstruct-13B-v0.1` | `mradermacher/TowerInstruct-13B-v0.1-GGUF`, `LoneStriker/TowerInstruct-13B-v0.1-GGUF` | 8.0 GB |
| `TowerInstruct-7B-v0.2` / `-Mistral-7B-v0.2` | `tensorblock/TowerInstruct-7B-v0.2-GGUF`, `bt1337/TowerInstruct-7B-v0.2-Q4_0-GGUF` | not individually confirmed (Q4_0 variant found, not Q4_K_M) |
| `Tower-Plus-9B` | `mradermacher/Tower-Plus-9B-GGUF` (+ `-i1-GGUF` imatrix variant), `tensorblock/Unbabel_Tower-Plus-9B-GGUF` | 5.76 GB |
| `Tower-Plus-72B` | `mradermacher/Tower-Plus-72B-i1-GGUF` | 47.4 GB |
| `Tower-Plus-2B` | **none found** in this pass — no dedicated community GGUF repo turned up in Hugging Face search, unlike every other size above | n/a |

All of the above are plain llama.cpp-format GGUF files, so anywhere Ollama
or LM Studio is already used, these load the same way the existing
`hf.co/s3nh/...:Q4_K_M` model string does today (`ollama pull
hf.co/<repo>:<quant>` / LM Studio's built-in Hugging Face search). vLLM also
accepts GGUF files directly, in addition to its native (non-quantized or
AWQ/GPTQ) checkpoint-loading path — so vLLM is not mutually exclusive with
the GGUF files in this table, it's an alternative *and* a valid loader for
them.

**Prompt templates — quoted exactly as documented:**

Generation 1 (TowerInstruct, all sizes/variants checked) uses **ChatML**,
verbatim from the model card:
```
<|im_start|>user
{USER PROMPT}<|im_end|>
<|im_start|>assistant
{MODEL RESPONSE}<|im_end|>
```
with a worked translation example on the same card:
```
<|im_start|>user
Translate the following text from Portuguese into English.
Portuguese: Um grupo de investigadores lançou um novo modelo para tarefas relacionadas com tradução.
English:<|im_end|>
<|im_start|>assistant
```

**This project's current `ollama_scorer.py` does not use this template.**
`_build_prompt()` wraps its instruction in `[INST] ... [/INST]` tags — a
Mistral/Llama-2-chat-style convention, not TowerInstruct's own documented
ChatML format. This is a concrete, actionable finding: the currently
configured model (`TowerInstruct-7B-v0.1`, Llama-2-based) is very likely
being prompted in a format it was not instruction-tuned on, which may
itself be *part of* why its free-text output "doesn't reliably carry
per-error severity" (the module's own code comment) — that comment
attributes the unreliability entirely to the model's inherent free-text
style, but an unmatched prompt template is a confounding variable that
comment doesn't rule out. Worth a follow-up experiment (not done here:
re-running the same eval pairs through the documented ChatML template and
comparing output structure) before concluding TowerInstruct's evaluation
mode is inherently unstructured.

Tower+'s cards show a plainer instruction style rather than a hand-written
chat-tag example, e.g. (from `Tower-Plus-9B`'s card, verbatim):
```
Translate the following English source text to Portuguese (Portugal):
English: Hello world!
Portuguese (Portugal):
```
and (from the paper's own template family, arXiv:2506.17080 HTML,
paraphrased where the exact punctuation wasn't recoverable from the
rendered text): "Translate the source text from [source language] to
[target language]. Source: [text] Target:". Because Tower+'s three released
sizes sit on **two different base-model families** (Gemma 2 for 2B/9B, Qwen
2.5 for 72B) — unlike Generation 1, where every size shared one Llama-2/
ChatML lineage — the safer implementation approach for Tower+ specifically
is to call `tokenizer.apply_chat_template()` from each checkpoint's own
`transformers` tokenizer config rather than hand-writing a single shared
wrapper string, since Gemma 2 and Qwen 2.5 do not share the same native
special-token chat format and a hand-rolled ChatML wrapper (correct for
Generation 1) would not necessarily be correct for Tower+.

An evaluation-task-specific prompt template (for either generation) was
**not found verbatim in any primary source reached in this pass** — see
§10.2's caveat. This project's own `_build_prompt()` in `ollama_scorer.py`
is the closest thing to a documented "Tower evaluation prompt" that exists
in any source touched during this research, and it is a peripateticware-era
hand-written prompt, not one sourced from Unbabel's own documentation.

**Citations:** `https://huggingface.co/Unbabel/TowerInstruct-7B-v0.1`,
`https://huggingface.co/Unbabel/Tower-Plus-9B`,
`https://huggingface.co/Unbabel/Tower-Plus-72B`,
`https://huggingface.co/s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF`,
`https://huggingface.co/mradermacher/TowerInstruct-13B-v0.1-GGUF`,
`https://huggingface.co/mradermacher/Tower-Plus-9B-GGUF`,
`https://huggingface.co/mradermacher/Tower-Plus-72B-i1-GGUF`,
`https://huggingface.co/tensorblock/Unbabel_Tower-Plus-9B-GGUF`,
`app/core/scoring/ollama_scorer.py` (this repo).

### 10.4 Compute footprint (4-bit GGUF, same reporting convention as §3's COMET sizes)

| Model | Params | Q4_K_M file size | Rough working VRAM/RAM (file size + KV-cache/runtime overhead) |
|---|---|---|---|
| `Tower-Plus-2B` | 2B | not found (est. ~1.7–2.0 GB by analogy to other Gemma-2-2B GGUF conversions — **not a verified figure**) | ~3–4 GB |
| `TowerBase-7B-v0.1` / `TowerInstruct-7B-v0.1` | 7B | 4.08 GB (confirmed) | ~6–8 GB |
| `Tower-Plus-9B` | 9B | 5.76 GB (confirmed) | ~8–10 GB |
| `TowerBase-13B-v0.1` / `TowerInstruct-13B-v0.1` | 13B | 8.0 GB (confirmed) | ~10–13 GB |
| `Tower-Plus-72B` | 73B | 47.4 GB (confirmed) | ~52–64 GB, realistically a single 48GB+ GPU or multi-GPU/unified-memory setup |

The 7B/13B rows are directly comparable in shape to already-adopted COMET
checkpoints (§3.1: `wmt22-cometkiwi-da` un-quantized; §9.2:
`wmt23-cometkiwi-da-xl` needs a stated 15GB minimum GPU, `-xxl` needs 44GB)
— Tower's 4-bit-quantized 7B/9B/13B sizes are **meaningfully lighter** than
even the mid-size COMET-Kiwi variants, and comparable to or lighter than
this project's already-configured default GGUF. `Tower-Plus-72B` is the
outlier: at 47.4GB for just the 4-bit weights (before KV-cache/context
overhead), it sits past even `wmt23-cometkiwi-da-xxl`'s stated 44GB minimum
and is flatly incompatible with this project's stated "no GPU infra
assumed by default" posture (§3.1) — CPU-only inference on a 73B model,
even quantized, would be extremely slow and is not a realistic fit for
anything but a rare, deliberately offline batch job.

**Citations:** `https://huggingface.co/s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF`,
`https://huggingface.co/mradermacher/TowerInstruct-13B-v0.1-GGUF`,
`https://huggingface.co/mradermacher/Tower-Plus-9B-GGUF`,
`https://huggingface.co/mradermacher/Tower-Plus-72B-i1-GGUF`.

### 10.5 How Tower/Tower+ evaluation compares to this project's existing scorers

This is the question the recommendation in §10.6 actually turns on, so it's
worth being precise about the *category* difference, not just listing
features side by side.

- **`ClaudeQualityScorer` (`app/core/scoring/claude_scorer.py`)** — a
  general-purpose frontier LLM, prompted with an explicit MQM-Core error
  taxonomy (`mqm_types.py`), returning structured JSON: typed
  `error_type` + `severity` per error, a `hard_fail` flag on any critical
  error, reference-free (source + target only, no reference field in the
  prompt — read directly from `claude_scorer.py`'s `user_msg` construction).
- **COMET-Kiwi (`app/core/scoring/automatic/comet_kiwi.py`)** — a
  **trained regression model** (encoder + regression head on top of
  InfoXLM), not a generative LLM at all. It outputs one learned scalar in
  [0,1], reference-free, with no error typing or severity of any kind. It
  is architecturally a completely different kind of signal from either LLM
  judge — this is why §7.2 of this doc already treats it as an independent
  axis rather than blending it into the Claude-scorer's score field.
- **Tower/Tower+'s "Machine Translation Evaluation" task** — per §10.2, a
  **generative LLM** (translation-specialized, not general-purpose) being
  prompted to produce a judgment in natural language/structured text, in
  principle either MQM-style (error spans + severity) or DA-style (scalar),
  depending on training-data-mirroring prompt design that isn't confirmed
  (§10.2's caveat) — but *categorically*, this is the same kind of thing
  `ClaudeQualityScorer` already is: an LLM asked to critique a translation,
  not a trained regression head like COMET-Kiwi.

**Direct answer to the task's question:** Tower/Tower+'s evaluation mode is
**not** a third distinct signal the way COMET-Kiwi is. It sits in the same
category as `ClaudeQualityScorer` — both are LLM-as-judge approaches — so
it **overlaps/competes with the Claude scorer's role**, not COMET-Kiwi's.
The meaningful differences from Claude are about *model strength and
hosting*, not *category of signal*: Tower is a much smaller (7B–73B),
translation-specialized, self-hostable open-weight model versus a much
larger general-purpose frontier model called over an API — the same
tradeoff this project already made a judgment call on in
`ollama_scorer.py`'s own design (treat the local model's flag as coarse
pass/fail, not a trusted severity breakdown, precisely because it's judged
less reliable than the Claude judge it exists alongside). Nothing found in
this research pass changes that judgment call; if anything, §10.2's
un-confirmed exact-schema/reference-format caveats are a reason for
*more* caution about trusting Tower's evaluation output structurally, not
less.

**Reference-free status, the specific constraint this project keeps hitting
(§3.2, §4.5, §9.3):** Tower's evaluation task is *plausibly* usable
reference-free — this project's own existing `ollama_scorer.py` already
calls it that way today (source + target only, no reference argument
anywhere in `_build_prompt()`) — but, per §10.2, whether Unbabel's own
training data taught the model to expect a reference was **not confirmed**.
COMET-Kiwi, by contrast, is *documented* as reference-free by design (§3.1,
directly from the COMET README) — a stronger, primary-source-backed claim
than anything available for Tower's evaluation mode. If reference-free
reliability is the deciding factor, COMET-Kiwi's claim to it is better
evidenced than Tower's.

**Citations:** `app/core/scoring/claude_scorer.py`,
`app/core/scoring/automatic/comet_kiwi.py` (both this repo),
plus all §10.1/§10.2 citations above.

### 10.6 Benchmark comparisons — Tower/Tower+ vs. COMET/COMET-Kiwi/XCOMET

**Tower as a translation *system*, evaluated by COMET/XCOMET (confirmed):**
Tower has a real, verifiable WMT track record — but as the thing being
scored, not as the scorer. "Tower v2: Unbabel-IST 2024 Submission for the
General MT Shared Task" (WMT 2024, `aclanthology.org/2024.wmt-1.12`) scaled
Tower up to 70B parameters (`Unbabel-Tower70B`) and, per the paper and
independent summary coverage, **ranked first across all 11 language pairs
by aggregate automatic-metric ranking** (COMET among them) and first in 8
of 11 pairs by human evaluation, in WMT24's General Translation shared
task. The Tower+ paper (arXiv:2506.17080) continues this pattern,
benchmarking Tower+ *as a translation system* against xCOMET-XXL,
MetricX-24-XXL, chrF, and COMET-22 on WMT24++ (e.g. Tower+-9B: xCOMET-XXL
84.38–86.25 depending on the language-pair subset reported; Tower+-72B:
xCOMET-XXL ~83–87 depending on subset) — these are all cases of **COMET-
family metrics scoring Tower**, the mirror image of what the task asked
about.

**Tower as an evaluation *metric*, submitted to WMT Metrics/QE shared
tasks — not found.** This is a real, checked-for negative finding, reported
the same way §5 (MEDAL) and §9's "no LLM-specific tuning claim" finding
were: searches for Tower/TowerInstruct/Tower+ as a participant in the WMT
Metrics or Quality Estimation shared tasks (the same shared tasks whose
2021–2025 papers are already catalogued in §6's Alon Lavie bibliography —
Rei et al.'s COMET/CometKiwi submissions appear in nearly every one of
those years) turned up **no submission record naming Tower as a metrics/QE
participant**, and the Tower+ paper's own related-work framing describes
Tower+'s translations being *judged by* xCOMET-XXL/MetricX-24-XXL rather
than describing Tower+ itself as a competing metric. This is a meaningful
asymmetry for this project's decision: **COMET/COMET-Kiwi/XCOMET have
multi-year, peer-reviewed, human-correlation benchmark numbers from the
exact shared tasks that are the field's standard for "does this metric
actually agree with human judges"** (§6's bibliography); **Tower's
evaluation mode has no equivalent independent validation found anywhere in
this research pass.** That doesn't mean Tower's evaluation output is bad —
it means nobody has published the kind of correlation-with-human-MQM number
for it that exists for every COMET-family checkpoint already in this doc,
so any claim about how good Tower's evaluation judgments are would be
unverified opinion, not benchmark fact.

**Citations:** `https://aclanthology.org/2024.wmt-1.12/`,
`https://arxiv.org/abs/2506.17080`,
`https://arxiv.org/html/2506.17080v1`,
plus §6's existing WMT21–25 Metrics/QE shared-task citations (not
re-listed here since they're already fully cited in that section, and
their content didn't change — only the "does Tower appear as a
participant" question was newly checked against them).

### 10.7 Recommendation

**Translation backend: yes, add Tower+ as one of the new multi-provider
translation options — specifically `Tower-Plus-9B`, served via Ollama GGUF
by default.** It has a real (if self-reported, not independently
replicated) competitive WMT24++ track record against GPT-4o/Claude-3.7
(§10.6), a 5.76GB Q4_K_M footprint that comfortably fits this project's
"no GPU infra assumed" posture (§10.4 — lighter than this project's already
-adopted COMET-Kiwi checkpoint), and a confirmed community GGUF conversion
path already proven out by the existing TowerInstruct-7B integration. This
is a genuinely new capability worth adding, not a redundant one.

**Evaluation backend: add it as a low-confidence, free, local *fallback/
secondary* signal only — do not position it as a peer of `ClaudeQualityScorer`
or COMET-Kiwi.** Per §10.5, Tower's evaluation mode is the same *category*
of signal as the Claude MQM scorer (LLM-as-judge) running on a much smaller,
translation-specialized, and — per §10.6 — externally unbenchmarked model.
It does not fill the gap COMET-Kiwi fills (a categorically distinct,
trained-regression signal); it competes with Claude's role instead, at
lower and unverified reliability. Concretely:
1. **Keep today's coarse pass/fail treatment** (`ScoreResult(score=40 or
   100, ...)` in `ollama_scorer.py`) rather than upgrading Tower's output
   to typed MQM errors the way `ClaudeQualityScorer` does — §10.2's
   confirmed finding (evaluation data mixes MQM-style and DA-style
   examples with no verified output schema) means trusting a parsed
   severity/error-type out of Tower's free text would be building
   structure on top of an unconfirmed contract.
2. **Fix the prompt template before evaluating whether Tower's output
   quality improves** — §10.3 found `ollama_scorer.py` uses `[INST]...
   [/INST]` tags, not TowerInstruct's documented ChatML format. This is a
   free, concrete, low-risk correctness fix independent of any Tower+
   adoption decision.
3. **If upgrading the model itself, prefer `Tower-Plus-9B` over the
   currently-configured `TowerInstruct-7B-v0.1`** for the evaluation role
   too (same model as the translation recommendation above, one fewer
   model to keep warm/cached locally) — but re-validate empirically (not
   done in this research pass) that its free-text evaluation output is at
   least as parseable as the current model's, since no primary source
   confirms Tower+ evaluation output structure either.
4. **Position clearly in the architecture, per §10.5:** Tower's evaluation
   mode is a candidate *replacement or backstop for the Claude scorer* in
   environments/requests where an API call isn't wanted (cost, latency,
   offline), not a new independent scoring axis alongside COMET-Kiwi. If
   this project ever needs a genuinely new/independent third signal beyond
   Claude and COMET-Kiwi, this research pass did not find that Tower's
   evaluation mode is it.

**Serving path, given no GPU infra is assumed by default:** **Ollama GGUF**
remains the right default for both roles, for the same reason it already is
today — it requires no new infrastructure this project doesn't already
depend on (`OLLAMA_URL`, `ollama_qe_model` already exist in `config.py`),
and the confirmed 5.76GB `Tower-Plus-9B` Q4_K_M file is realistic on a
laptop/small-VM CPU or modest consumer GPU. **vLLM is Unbabel's own stated
preferred path for Tower+** (§10.3) and should be documented as the
upgrade path *if and when* this project ever provisions GPU infra — it is
not a reason to delay adoption via Ollama today. **LM Studio** is a
functionally equivalent alternative to Ollama for any of the GGUF files in
§10.3's table (same llama.cpp runtime underneath) and fits naturally if
this project's multi-provider architecture wants a desktop/dev-machine
target distinct from a server-side Ollama daemon, but doesn't change the
underlying recommendation. **`Tower-Plus-72B` should not be part of the
default recommendation at all** — 47.4GB of 4-bit weights alone is
incompatible with "no GPU infra assumed," and no benchmark evidence found
in this pass suggests the translation-quality or evaluation-quality gain
over the 9B model is large enough to justify that jump for this project's
purposes (mirroring §9.2's identical reasoning for why
`wmt23-cometkiwi-da-xl/xxl` weren't recommended over the smaller
`wmt22-cometkiwi-da`).

**What was not verified, stated plainly (mirroring §9.4's honesty
convention):**
- No verbatim example of Tower's "Machine Translation Evaluation" training
  data was obtained, so the exact prompt/output schema for that task —
  and whether it's reference-based or reference-free as trained — remains
  unconfirmed (§10.2).
- No independent benchmark of Tower/Tower+'s evaluation-mode correlation
  with human judgment (the WMT-Metrics-shared-task-style number that
  exists for every COMET-family checkpoint in this doc) was found to exist
  at all, not just "not reached in this pass" (§10.6).
- `TowerInstruct-13B-v0.2`'s own model card was not independently fetched
  (only referenced by a sibling card) — its license/size in §10.1's table
  is marked accordingly.
- `Tower-Plus-2B`'s GGUF footprint is an analogy-based estimate, not a
  confirmed file size — no dedicated community GGUF repo for it was found
  in this pass (§10.3, §10.4).
- Whether `s3nh`'s "openrail" license tag on the currently-configured GGUF
  repo has any actual legal effect distinct from the underlying
  CC-BY-NC-4.0 terms was not resolved by contacting either party — flagged
  as a re-uploader tag that shouldn't be relied on, not as a confirmed
  license conflict requiring action.

**Citations:** all citations from §10.1–§10.6 above, plus this repo's
`app/core/scoring/ollama_scorer.py` and `app/core/config.py`.
