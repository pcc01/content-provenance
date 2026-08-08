"""Tests for Phase 13's style-adherence scoring (app/core/scoring/style_*.py),
its redrive-threshold wiring (app/core/redrive/engine.py), and the
ContextRetrieval/StyleAdherenceAssessment provenance it produces
(app/core/prov_builder.py §4d/§4e). Mirrors tests/test_redrive.py's
_StubScorer pattern — no real ANTHROPIC_API_KEY needed.
Run with: PYTHONPATH=. pytest tests/test_style_scoring.py -v
"""

from typing import Optional

import pytest

from app.core.database import get_db, init_db
from app.core.graph.builder import record_unit_style_context
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.style_base import StyleScorer, StyleScoreResult
from app.core.scoring.style_factory import get_style_scorer, score_unit_style
from app.core.translation_backends import MockTranslationBackend
from app.models.schemas import (
    GlossaryTerm,
    RedriveRun,
    RetrievedFact,
    StyleContextRetrieval,
    StyleGuide,
    StyleGuideRule,
    StyleRuleType,
    TranslationMethod,
    TranslationUnit,
)


class _StubQualityScorer(QualityScorer):
    async def score(self, unit: TranslationUnit) -> ScoreResult:
        return ScoreResult(score=95)  # always passes quality — isolates the style axis


class _StubStyleScorer(StyleScorer):
    """Off-brand whenever the text contains "off-brand" — deterministic and
    offline."""

    async def score_text(
        self, text: str, language: str,
        context: Optional[StyleContextRetrieval] = None, reference_text: Optional[str] = None,
    ) -> StyleScoreResult:
        if "off-brand" in text:
            return StyleScoreResult(tone_score=10, voice_score=10, terminology_score=10, overall_score=10,
                                     reasons=["off_brand_phrasing"])
        return StyleScoreResult(tone_score=95, voice_score=95, terminology_score=95, overall_score=95)


@pytest.mark.asyncio
async def test_score_unit_style_persists_and_is_retrievable():
    await init_db()
    db = get_db()

    agent = await db.get_or_create_agent("test-style-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-style-1", source_text="Welcome aboard!", source_language="en-US",
        target_text="Bienvenue à bord !", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    record = await score_unit_style(unit, style_guide_id="guide-1", scorer=_StubStyleScorer())
    assert record.overall_score == 95

    latest = await db.get_latest_style_adherence_score(unit.id)
    assert latest.id == record.id
    assert latest.overall_score == 95


@pytest.mark.asyncio
async def test_style_scorer_failure_degrades_to_needs_review_not_a_crash():
    await init_db()
    db = get_db()

    class _BrokenScorer(StyleScorer):
        async def score_text(self, *args, **kwargs):
            raise RuntimeError("simulated scorer outage")

    agent = await db.get_or_create_agent("test-style-agent-2", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-style-2", source_text="Hello.", source_language="en-US",
        target_text="Bonjour.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    record = await score_unit_style(unit, scorer=_BrokenScorer())
    assert record.overall_score is None
    assert record.needs_review is True
    assert "scorer_error" in record.reasons


@pytest.mark.asyncio
async def test_redrive_engine_redrives_on_style_threshold_alone():
    """Quality always passes (_StubQualityScorer) — only the style axis is
    below threshold, and that alone must still trigger a redrive."""
    await init_db()
    db = get_db()

    agent = await db.get_or_create_agent("test-redrive-style-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-redrive-style", source_text="Some copy.", source_language="en-US",
        target_text="Some off-brand copy.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(
        scorer=_StubQualityScorer(), scorer_label="stub-quality",
        redrive_backend=MockTranslationBackend(), style_scorer=_StubStyleScorer(),
    )
    run = RedriveRun(
        threshold=50,  # quality threshold — _StubQualityScorer always scores 95, never below this
        style_threshold=50, style_guide_id="guide-1",
        scope={"unit_ids": [unit.id]}, scoring_provider="stub-quality", redrive_provider="mock",
    )
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["redriven"] == 1
    item = completed.items[0]
    assert item.outcome.value == "redriven"

    updated_unit = await db.get_translation_unit(unit.id)
    assert updated_unit.target_text.startswith("[FR]")  # MockTranslationBackend's marker

    # The style scorer's reason made it into the version note alongside the
    # quality reasons — confirms the style axis, not just quality, drove
    # this redrive (quality was always 95, well above its threshold of 50).
    versions = await db.list_translation_unit_versions(unit.id)
    assert "style:off_brand_phrasing" in (versions[-1].note or "")

    # The new (on-brand, per MockTranslationBackend's output) text was
    # re-scored for style as part of the redrive.
    latest_style = await db.get_latest_style_adherence_score(unit.id)
    assert latest_style.overall_score == 95


@pytest.mark.asyncio
async def test_redrive_engine_skips_when_both_axes_pass():
    await init_db()
    db = get_db()

    agent = await db.get_or_create_agent("test-redrive-style-agent-2", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-redrive-style-2", source_text="Some copy.", source_language="en-US",
        target_text="Some on-brand copy.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(
        scorer=_StubQualityScorer(), scorer_label="stub-quality",
        redrive_backend=MockTranslationBackend(), style_scorer=_StubStyleScorer(),
    )
    run = RedriveRun(
        threshold=50, style_threshold=50, style_guide_id="guide-1",
        scope={"unit_ids": [unit.id]}, scoring_provider="stub-quality", redrive_provider="mock",
    )
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["redriven"] == 0
    assert completed.summary["skipped_above_threshold"] == 1


def test_style_scorer_factory_rejects_unknown_provider():
    with pytest.raises(RuntimeError):
        get_style_scorer("not-a-real-provider")


@pytest.mark.asyncio
async def test_context_retrieval_and_style_assessment_appear_in_provenance():
    """End-to-end: link a unit to a rule/term via the graph (as the
    translation flow does — app/core/graph/builder.record_unit_style_context),
    score it, and confirm prov_builder.py surfaces both the ContextRetrieval
    activity (§4d) and the StyleAdherenceAssessment activity (§4e)."""
    from app.core.prov_builder import build_provenance_record

    await init_db()
    db = get_db()

    guide = StyleGuide(name="Prov Test Guide")
    await db.save_style_guide(guide)
    rule = StyleGuideRule(style_guide_id=guide.id, rule_type=StyleRuleType.TONE, rule_text="Stay upbeat.")
    term = GlossaryTerm(source_term="workspace", target_term="workstation")
    await db.save_style_guide_rule(rule)
    await db.save_glossary_term(term)

    agent = await db.get_or_create_agent("test-prov-style-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-prov-style", source_text="Welcome to your workspace.", source_language="en-US",
        target_text="Bienvenue dans votre espace de travail.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    retrieval = StyleContextRetrieval(
        rules=[RetrievedFact(kind="rule", id=rule.id, text=rule.rule_text)],
        terms=[RetrievedFact(kind="term", id=term.id, text=f"{term.source_term} -> {term.target_term}")],
        style_guide_id=guide.id,
    )
    await record_unit_style_context(unit.id, retrieval)
    await score_unit_style(unit, style_guide_id=guide.id, scorer=_StubStyleScorer())

    prov = await build_provenance_record(unit)

    assert any(a.activity_type == "ContextRetrieval" for a in prov.activities)
    assert any(a.activity_type == "StyleAdherenceAssessment" for a in prov.activities)
    assert any(e.entity_type == "StyleGuideRule" for e in prov.entities)
    assert any(e.entity_type == "GlossaryTerm" for e in prov.entities)
    assert any(
        r["type"] == "wasInformedBy" and r.get("informant", "").startswith("activity:context-retrieval:")
        for r in prov.relations
    )

    # §9b.3 — the same retrieved facts render as a human-readable style
    # brief note in the exported XLIFF, not just as PROV entity soup, so a
    # vendor's linguist (not just an AI backend) gets the same grounding.
    # Mirrors app/api/xliff_export.py's real single-unit export call shape
    # (build_single_unit_xliff deliberately builds with NO provenance).
    from app.xliff.xliff_service import build_xliff_document

    xml = build_xliff_document(
        units=[unit], provenance_records={unit.id: prov}, deployments={unit.id: []},
        project_name="style-brief-test", doc_id=unit.id,
    )
    assert 'styleBrief' in xml
    assert 'Stay upbeat.' in xml
    assert 'workstation' in xml

