"""Tests for Phase 13's graph layer (app/core/db/repository.py's graph
methods + app/core/graph/) — node/edge upsert-dedup, one-hop neighbor
traversal, the supersedes_id chain, and retrieve_style_context's
locale/keyword fallback when no embedding model is available (the common
case in this test environment — see app/core/graph/embeddings.py).
Run with: PYTHONPATH=. pytest tests/test_graph.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.graph import builder as graph_builder
from app.core.graph.retrieval import retrieve_style_context
from app.models.schemas import (
    GlossaryTerm,
    StyleGuide,
    StyleGuideRule,
    StyleRuleSeverity,
    StyleRuleType,
)


@pytest.mark.asyncio
async def test_graph_node_upsert_is_idempotent():
    await init_db()
    db = get_db()

    node1 = await db.upsert_graph_node("Unit", "translation_units", "unit-abc", label="first")
    node2 = await db.upsert_graph_node("Unit", "translation_units", "unit-abc", label="second")

    assert node1.id == node2.id
    fetched = await db.get_graph_node("Unit", "unit-abc")
    assert fetched.label == "second"  # second upsert's label wins, same row


@pytest.mark.asyncio
async def test_graph_edge_upsert_dedups_and_neighbors_both_directions():
    await init_db()
    db = get_db()

    unit_node = await db.upsert_graph_node("Unit", "translation_units", "unit-edge-1")
    rule_node = await db.upsert_graph_node("StyleGuideRule", "style_guide_rules", "rule-edge-1")

    await db.upsert_graph_edge(unit_node.id, rule_node.id, "appliedRule")
    await db.upsert_graph_edge(unit_node.id, rule_node.id, "appliedRule")  # re-recorded, must not duplicate

    out_neighbors = await db.list_neighbors(unit_node.id, edge_type="appliedRule", direction="out")
    assert [n.id for n in out_neighbors] == [rule_node.id]

    in_neighbors = await db.list_neighbors(rule_node.id, edge_type="appliedRule", direction="in")
    assert [n.id for n in in_neighbors] == [unit_node.id]


@pytest.mark.asyncio
async def test_link_unit_style_context_creates_both_edge_types():
    await init_db()
    db = get_db()

    guide = StyleGuide(name="Link Test Guide")
    await db.save_style_guide(guide)
    rule = StyleGuideRule(
        style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Be upbeat.",
    )
    term = GlossaryTerm(source_term="workspace", target_term="workstation")
    await db.save_style_guide_rule(rule)
    await db.save_glossary_term(term)

    await db.link_unit_style_context("unit-link-1", [rule.id], [term.id])

    unit_node = await db.get_graph_node("Unit", "unit-link-1")
    rule_neighbors = await db.list_neighbors(unit_node.id, edge_type="appliedRule", direction="out")
    term_neighbors = await db.list_neighbors(unit_node.id, edge_type="usedTerm", direction="out")
    assert rule_neighbors[0].ref_id == rule.id
    assert term_neighbors[0].ref_id == term.id


@pytest.mark.asyncio
async def test_style_guide_supersedes_chain():
    await init_db()
    db = get_db()

    v1 = StyleGuide(name="Brand Voice", version="1.0")
    await db.save_style_guide(v1)
    v2 = StyleGuide(name="Brand Voice", version="2.0", supersedes_id=v1.id)
    await db.save_style_guide(v2)
    v3 = StyleGuide(name="Brand Voice", version="3.0", supersedes_id=v2.id)
    await db.save_style_guide(v3)

    chain = await db.get_style_guide_chain(v3.id)
    assert [g.version for g in chain] == ["3.0", "2.0", "1.0"]


@pytest.mark.asyncio
async def test_sibling_rules_excludes_self_and_scopes_to_guide():
    await init_db()
    db = get_db()

    guide = StyleGuide(name="Sibling Test Guide")
    await db.save_style_guide(guide)
    r1 = StyleGuideRule(style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Rule one")
    r2 = StyleGuideRule(style_guide_id=guide.id, rule_type=StyleRuleType.VOICE, rule_text="Rule two")
    other_guide = StyleGuide(name="Unrelated Guide")
    await db.save_style_guide(other_guide)
    r3 = StyleGuideRule(style_guide_id=other_guide.id, rule_type=StyleRuleType.TONE, rule_text="Unrelated rule")
    for r in (r1, r2, r3):
        await db.save_style_guide_rule(r)

    siblings = await graph_builder.sibling_rules(guide.id, exclude_rule_id=r1.id)
    sibling_ids = {s.id for s in siblings}
    assert r2.id in sibling_ids
    assert r1.id not in sibling_ids
    assert r3.id not in sibling_ids


@pytest.mark.asyncio
async def test_glossary_preferred_over_traversal():
    await init_db()
    db = get_db()

    deprecated = GlossaryTerm(source_term="workspace", target_term="workspace (old)")
    preferred = GlossaryTerm(source_term="workstation", target_term="workstation")
    await db.save_glossary_term(deprecated)
    await db.save_glossary_term(preferred)

    await graph_builder.link_preferred_over(deprecated.id, [preferred.id])

    alternatives = await db.list_glossary_preferred_alternatives(deprecated.id)
    assert [a.id for a in alternatives] == [preferred.id]


@pytest.mark.asyncio
async def test_retrieve_style_context_falls_back_without_embeddings_and_expands_siblings():
    """No embedding model is installed in this test environment (see
    app/core/graph/embeddings.py) — retrieval must fall back to locale
    filtering rather than raising, and still perform the graph expansion
    step (sibling rules in the same guide)."""
    await init_db()
    db = get_db()

    guide = StyleGuide(name="Fallback Test Guide", locale="fr-FR")
    await db.save_style_guide(guide)
    seed_rule = StyleGuideRule(
        style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Keep it warm and friendly.",
        applies_to_locale="fr-FR", severity=StyleRuleSeverity.MAJOR,
    )
    sibling_rule = StyleGuideRule(
        style_guide_id=guide.id, rule_type=StyleRuleType.VOICE, rule_text="Never sound robotic.",
        applies_to_locale="fr-FR",
    )
    await db.save_style_guide_rule(seed_rule)
    await db.save_style_guide_rule(sibling_rule)

    do_not_translate = GlossaryTerm(source_term="WordInBits", do_not_translate=True, locale="fr-FR")
    await db.save_glossary_term(do_not_translate)

    result = await retrieve_style_context(
        "Welcome to WordInBits.", "en-US", "fr-FR", style_guide_id=guide.id,
    )

    rule_ids = {f.id for f in result.rules}
    assert seed_rule.id in rule_ids
    assert sibling_rule.id in rule_ids  # graph-expanded, not just the "vector"-seeded match

    term_texts = " ".join(f.text for f in result.terms)
    assert "Do not translate" in term_texts  # exact-mention fallback caught the literal brand name

    prompt = result.as_prompt_context()
    assert "Keep it warm and friendly." in prompt
    assert not result.is_empty
