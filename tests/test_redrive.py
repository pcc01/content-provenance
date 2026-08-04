"""
Tests for the threshold-quality redrive engine (Phase 3).
Run with: PYTHONPATH=. pytest tests/test_redrive.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.translation_backends import MockTranslationBackend
from app.models.schemas import RedriveRun, TranslationMethod, TranslationUnit


class _StubScorer(QualityScorer):
    """Scores anything that still looks untranslated (target == source) as 0,
    everything else as 90 — deterministic and offline, so these tests don't
    depend on a real Claude/Ollama scorer being configured."""

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        if not unit.target_text or unit.target_text == unit.source_text:
            return ScoreResult(score=0, reasons=["untranslated"], deterministic=True)
        return ScoreResult(score=90)


@pytest.mark.asyncio
async def test_redrive_engine_redrives_below_threshold_and_updates_provenance():
    await init_db()
    db = get_db()

    agent = await db.get_or_create_agent("test-redrive-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-redrive", source_text="Needs a real translation.",
        source_language="en-US", target_text="Needs a real translation.",  # simulated bad/untranslated content
        target_language="fr-FR", translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_StubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend())
    run = RedriveRun(
        threshold=50, scope={"unit_ids": [unit.id]},
        scoring_provider="stub", redrive_provider="mock",
    )
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["redriven"] == 1
    assert len(completed.items) == 1
    item = completed.items[0]
    assert item.before_score == 0
    assert item.after_score == 90
    assert item.outcome.value == "redriven"

    updated_unit = await db.get_translation_unit(unit.id)
    assert updated_unit.target_text != "Needs a real translation."
    assert updated_unit.target_text.startswith("[FR]")

    versions = await db.list_translation_unit_versions(unit.id)
    assert len(versions) == 2
    assert versions[-1].source_event == "redrive"
    assert "mock" in (versions[-1].note or "")  # names the redrive (translation) provider, not the scorer

    prov = await db.get_provenance_by_unit(unit.id)
    assert any(r["type"] == "wasRevisionOf" for r in prov.relations)
    assert any(a.activity_type == "QualityAssessment" for a in prov.activities)


@pytest.mark.asyncio
async def test_redrive_preview_does_not_mutate_translations():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-preview-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-preview", source_text="Preview me.", source_language="en-US",
        target_text="Preview me.", target_language="de-DE", translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_StubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend())
    forecast = await engine.preview({"unit_ids": [unit.id]}, threshold=50)

    assert forecast["scope_count"] == 1
    assert forecast["below_threshold"] == 1

    unchanged = await db.get_translation_unit(unit.id)
    assert unchanged.target_text == "Preview me."  # preview must never redrive


@pytest.mark.asyncio
async def test_redrive_human_in_the_loop_approve():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-hitl-approve-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-hitl-approve", source_text="Human gate approve test.",
        source_language="en-US", target_text="Human gate approve test.",
        target_language="fr-FR", translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_StubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend())
    run = RedriveRun(
        threshold=50, scope={"unit_ids": [unit.id]}, scoring_provider="stub",
        redrive_provider="mock", require_human_approval=True,
    )
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["pending_approval"] == 1
    assert completed.summary["redriven"] == 0
    item = completed.items[0]
    assert item.outcome.value == "pending_approval"
    assert item.proposed_text is not None
    assert item.proposed_text.startswith("[FR]")

    # Nothing applied yet — the unit must be untouched until approved.
    untouched = await db.get_translation_unit(unit.id)
    assert untouched.target_text == "Human gate approve test."

    approved = await engine.approve_item(item.id, approved_by="reviewer@example.com")
    assert approved.outcome.value == "redriven"
    assert approved.after_score == 90
    assert approved.approved_by == "reviewer@example.com"

    updated_unit = await db.get_translation_unit(unit.id)
    assert updated_unit.target_text == item.proposed_text

    versions = await db.list_translation_unit_versions(unit.id)
    assert len(versions) == 2
    assert "approved by reviewer@example.com" in (versions[-1].note or "")


@pytest.mark.asyncio
async def test_redrive_human_in_the_loop_reject():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-hitl-reject-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-hitl-reject", source_text="Human gate reject test.",
        source_language="en-US", target_text="Human gate reject test.",
        target_language="de-DE", translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_StubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend())
    run = RedriveRun(
        threshold=50, scope={"unit_ids": [unit.id]}, scoring_provider="stub",
        redrive_provider="mock", require_human_approval=True,
    )
    await db.create_redrive_run(run)
    completed = await engine.run(run)
    item = completed.items[0]

    rejected = await engine.reject_item(item.id, rejected_by="reviewer@example.com", reason="not accurate enough")
    assert rejected.outcome.value == "rejected"
    assert "not accurate enough" in rejected.detail

    unchanged = await db.get_translation_unit(unit.id)
    assert unchanged.target_text == "Human gate reject test."  # rejection must not touch the unit

    versions = await db.list_translation_unit_versions(unit.id)
    assert len(versions) == 1  # no new version — nothing was ever applied


@pytest.mark.asyncio
async def test_redrive_skips_units_above_threshold():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-skip-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-skip", source_text="Already fine.", source_language="en-US",
        target_text="Déjà bien.", target_language="fr-FR", translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_StubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend())
    run = RedriveRun(threshold=50, scope={"unit_ids": [unit.id]}, scoring_provider="stub", redrive_provider="mock")
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["skipped_above_threshold"] == 1
    assert completed.summary["redriven"] == 0
    unchanged = await db.get_translation_unit(unit.id)
    assert unchanged.target_text == "Déjà bien."
