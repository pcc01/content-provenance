"""The hybrid vector + graph retrieval this whole phase is for — see §4
Option 1 of docs/graphrag-provenance-proposal.md.

Vector search (pgvector cosine distance) seeds candidates from
style_guide_rules/glossary_terms/translation_exemplars; graph traversal
(app/core/graph/builder.py) expands them one hop (sibling rules in the
same guide, preferred-over glossary alternatives). Falls back to plain
locale/keyword filtering when no embedding model is available
(app/core/graph/embeddings.py) — retrieval never fails outright, it just
gets less precise.

Returns app.models.schemas.RetrievedFact objects — small, compact,
structured facts, never raw style-guide prose. This is the FactRAG lesson
from Barry et al. 2025 (§7 of the proposal doc): what makes retrieval both
cheap (fewer tokens) and auditable (a fact is a specific row with an id,
not an ambiguous span of a larger document).
"""

from typing import Optional

from app.core.database import get_db
from app.core.graph import builder as graph_builder
from app.core.graph.embeddings import embed_text
from app.models.schemas import (
    GlossaryTerm,
    RetrievedFact,
    StyleContextRetrieval,
    StyleGuideRule,
    TranslationExemplar,
)


async def retrieve_style_context(
    source_text: str,
    source_language: str,
    target_language: str,
    style_guide_id: Optional[str] = None,
    top_k: int = 5,
) -> StyleContextRetrieval:
    db = get_db()
    embedding = await embed_text(source_text)

    # ── Style guide rules ────────────────────────────────────────────────
    if embedding is not None:
        rules = await db.search_style_guide_rules(
            embedding, locale=target_language, style_guide_id=style_guide_id, limit=top_k,
        )
    else:
        rules = await db.list_style_guide_rules(
            style_guide_id=style_guide_id, locale=target_language, limit=top_k,
        )

    seen_rule_ids = {r.id for r in rules}
    expanded_rules = list(rules)
    for r in rules[:2]:  # cap fan-out — only expand the top couple of matches
        for sibling in await graph_builder.sibling_rules(r.style_guide_id, exclude_rule_id=r.id, limit=3):
            if sibling.id not in seen_rule_ids and len(expanded_rules) < top_k * 2:
                expanded_rules.append(sibling)
                seen_rule_ids.add(sibling.id)

    # ── Glossary terms ───────────────────────────────────────────────────
    if embedding is not None:
        terms = await db.search_glossary_terms(embedding, locale=target_language, limit=top_k)
    else:
        terms = await db.list_glossary_terms(style_guide_id=style_guide_id, locale=target_language, limit=top_k)

    # Exact-mention match always runs too (catches literal terminology an
    # embedding's fuzzy similarity can miss) and merges in, deduped.
    seen_term_ids = {t.id for t in terms}
    for t in await db.find_glossary_terms_mentioned_in(source_text, locale=target_language, limit=top_k):
        if t.id not in seen_term_ids:
            terms.append(t)
            seen_term_ids.add(t.id)

    expanded_terms = list(terms)
    for t in terms[:2]:
        for alt in await db.list_glossary_preferred_alternatives(t.id):
            if alt.id not in seen_term_ids and len(expanded_terms) < top_k * 2:
                expanded_terms.append(alt)
                seen_term_ids.add(alt.id)

    # ── Translation exemplars ────────────────────────────────────────────
    if embedding is not None:
        exemplars = await db.search_translation_exemplars(embedding, source_language, target_language, limit=top_k)
    else:
        exemplars = await db.list_translation_exemplars(source_language, target_language, limit=top_k)

    return StyleContextRetrieval(
        rules=[_rule_to_fact(r) for r in expanded_rules],
        terms=[_term_to_fact(t) for t in expanded_terms],
        exemplars=[_exemplar_to_fact(e) for e in exemplars],
        style_guide_id=style_guide_id,
    )


def _rule_to_fact(rule: StyleGuideRule) -> RetrievedFact:
    if rule.source_term and rule.target_term:
        locale_note = f" in {rule.applies_to_locale}" if rule.applies_to_locale else ""
        text = f"Use '{rule.target_term}' not '{rule.source_term}'{locale_note} — {rule.rule_text}"
    else:
        text = rule.rule_text
    return RetrievedFact(kind="rule", id=rule.id, text=text)


def _term_to_fact(term: GlossaryTerm) -> RetrievedFact:
    if term.do_not_translate:
        text = f"Do not translate '{term.source_term}' — keep as-is."
    elif term.target_term:
        locale_note = f" ({term.locale})" if term.locale else ""
        text = f"'{term.source_term}' -> '{term.target_term}'{locale_note}"
    else:
        text = f"'{term.source_term}'" + (f" — {term.notes}" if term.notes else "")
    return RetrievedFact(kind="term", id=term.id, text=text)


def _exemplar_to_fact(exemplar: TranslationExemplar) -> RetrievedFact:
    return RetrievedFact(
        kind="exemplar", id=exemplar.id,
        text=f'"{exemplar.source_text}" -> "{exemplar.target_text}"',
    )
