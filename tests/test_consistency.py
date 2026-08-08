"""Tests for Phase 14's cross-document/page consistency checker
(app/core/consistency/checker.py, app/api/consistency.py) — the O(k·n)
clustering technique from §7 of docs/graphrag-provenance-proposal.md.
Run with: PYTHONPATH=. pytest tests/test_consistency.py -v
"""

import pytest

from app.core.consistency.checker import run_consistency_check
from app.core.database import get_db, init_db
from app.models.schemas import (
    GlossaryTerm,
    StyleAdherenceScore,
    StyleGuide,
    StyleGuideRule,
    StyleRuleType,
    TranslationMethod,
    TranslationUnit,
)


async def _make_unit(db, agent_id, target_text, suffix):
    unit = TranslationUnit(
        source_id=f"src-consistency-{suffix}", source_text="Some copy.", source_language="en-US",
        target_text=target_text, target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent_id,
    )
    await db.save_translation_unit(unit)
    return unit


@pytest.mark.asyncio
async def test_terminology_inconsistency_flags_mixed_compliance():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("consistency-test-agent", "SoftwareAgent")

    term = GlossaryTerm(source_term="workspace", target_term="poste de travail")
    await db.save_glossary_term(term)

    good = await _make_unit(db, agent.id, "Bienvenue dans votre poste de travail.", "good")
    bad = await _make_unit(db, agent.id, "Bienvenue dans votre espace de travail.", "bad")
    await db.link_unit_style_context(good.id, [], [term.id])
    await db.link_unit_style_context(bad.id, [], [term.id])

    result = await run_consistency_check({"unit_ids": [good.id, bad.id]})
    findings = [f for f in result.findings if f.finding_type == "term_inconsistency"]
    assert len(findings) == 1
    assert findings[0].unit_ids == [bad.id]
    assert findings[0].detail["compliant_unit_ids"] == [good.id]


@pytest.mark.asyncio
async def test_terminology_drift_when_no_unit_complies():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("consistency-test-agent-2", "SoftwareAgent")

    term = GlossaryTerm(source_term="WordInBits", do_not_translate=True)
    await db.save_glossary_term(term)

    unit = await _make_unit(db, agent.id, "Bienvenue chez MotDansDesBits.", "translated-brand")
    await db.link_unit_style_context(unit.id, [], [term.id])

    result = await run_consistency_check({"unit_ids": [unit.id]})
    findings = [f for f in result.findings if f.finding_type == "term_drift"]
    assert len(findings) == 1
    assert findings[0].unit_ids == [unit.id]
    assert findings[0].severity == "info"


@pytest.mark.asyncio
async def test_no_terminology_finding_when_all_units_comply():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("consistency-test-agent-3", "SoftwareAgent")

    term = GlossaryTerm(source_term="workspace", target_term="poste de travail")
    await db.save_glossary_term(term)

    u1 = await _make_unit(db, agent.id, "Votre poste de travail est pret.", "compliant-1")
    u2 = await _make_unit(db, agent.id, "Acceder a votre poste de travail.", "compliant-2")
    await db.link_unit_style_context(u1.id, [], [term.id])
    await db.link_unit_style_context(u2.id, [], [term.id])

    result = await run_consistency_check({"unit_ids": [u1.id, u2.id]})
    assert not any(f.finding_type in ("term_drift", "term_inconsistency") for f in result.findings)


@pytest.mark.asyncio
async def test_tone_spread_flags_wide_variance_within_shared_rule():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("consistency-test-agent-4", "SoftwareAgent")

    guide = StyleGuide(name="Consistency Test Guide")
    await db.save_style_guide(guide)
    rule = StyleGuideRule(style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Stay upbeat.")
    await db.save_style_guide_rule(rule)

    upbeat = await _make_unit(db, agent.id, "Genial, bienvenue !", "upbeat")
    flat = await _make_unit(db, agent.id, "Bienvenue.", "flat")
    await db.link_unit_style_context(upbeat.id, [rule.id], [])
    await db.link_unit_style_context(flat.id, [rule.id], [])
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=upbeat.id, tone_score=95, scorer="stub"))
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=flat.id, tone_score=40, scorer="stub"))

    result = await run_consistency_check({"unit_ids": [upbeat.id, flat.id]})
    tone_findings = [f for f in result.findings if f.finding_type == "tone_spread"]
    assert len(tone_findings) == 1
    assert set(tone_findings[0].unit_ids) == {upbeat.id, flat.id}


@pytest.mark.asyncio
async def test_no_tone_finding_when_spread_within_threshold():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("consistency-test-agent-5", "SoftwareAgent")

    guide = StyleGuide(name="Consistency Test Guide 2")
    await db.save_style_guide(guide)
    rule = StyleGuideRule(style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Stay upbeat.")
    await db.save_style_guide_rule(rule)

    u1 = await _make_unit(db, agent.id, "Genial !", "close-1")
    u2 = await _make_unit(db, agent.id, "Super !", "close-2")
    await db.link_unit_style_context(u1.id, [rule.id], [])
    await db.link_unit_style_context(u2.id, [rule.id], [])
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=u1.id, tone_score=90, scorer="stub"))
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=u2.id, tone_score=85, scorer="stub"))

    result = await run_consistency_check({"unit_ids": [u1.id, u2.id]})
    assert not any(f.finding_type == "tone_spread" for f in result.findings)


@pytest.mark.asyncio
async def test_consistency_check_api(client):
    r = await client.post("/api/v1/style/guides", json={"name": "API Consistency Guide"})
    guide = r.json()
    r = await client.post(f"/api/v1/style/guides/{guide['id']}/rules", json={
        "rule_type": "tone", "rule_text": "Stay upbeat.",
    })
    rule = r.json()

    db = get_db()
    agent = await db.get_or_create_agent("consistency-api-agent", "SoftwareAgent")
    u1 = await _make_unit(db, agent.id, "Genial, bienvenue !", "api-upbeat")
    u2 = await _make_unit(db, agent.id, "Bienvenue.", "api-flat")
    await db.link_unit_style_context(u1.id, [rule["id"]], [])
    await db.link_unit_style_context(u2.id, [rule["id"]], [])
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=u1.id, tone_score=95, scorer="stub"))
    await db.save_style_adherence_score(StyleAdherenceScore(unit_id=u2.id, tone_score=40, scorer="stub"))

    r = await client.get("/api/v1/consistency/check", params={"unit_ids": f"{u1.id},{u2.id}"})
    assert r.status_code == 200
    data = r.json()
    assert data["units_checked"] == 2
    assert any(f["finding_type"] == "tone_spread" for f in data["findings"])
