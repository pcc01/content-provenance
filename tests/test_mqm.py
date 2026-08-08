"""Tests for Phase 15's MQM error taxonomy (app/core/scoring/mqm_types.py)
and the hard-fail redrive trigger it enables (app/core/redrive/engine.py).
Mirrors tests/test_style_scoring.py's stub-scorer pattern — no real
ANTHROPIC_API_KEY needed.
Run with: PYTHONPATH=. pytest tests/test_mqm.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.mqm_types import (
    MQM_ERROR_TYPE_DIMENSION,
    MQMDimension,
    MQMErrorType,
    build_prompt_rubric,
)
from app.core.translation_backends import MockTranslationBackend
from app.models.schemas import (
    RedriveRun,
    ScoreError,
    ScoreErrorSeverity,
    TranslationMethod,
    TranslationUnit,
)


def test_every_error_type_has_a_dimension_mapping():
    for error_type in MQMErrorType:
        assert error_type in MQM_ERROR_TYPE_DIMENSION, f"{error_type} has no dimension mapping"
        assert MQM_ERROR_TYPE_DIMENSION[error_type] in MQMDimension


def test_all_seven_dimensions_are_represented():
    dimensions_used = set(MQM_ERROR_TYPE_DIMENSION.values())
    assert dimensions_used == set(MQMDimension)


def test_dimension_level_entries_reuse_the_dimension_mnemonic():
    """The dimension-level error type (e.g. MQMErrorType.ACCURACY) must
    share its value with the dimension it belongs to (MQMDimension.ACCURACY)
    — MQM explicitly allows flagging at just the top level. Subtypes (e.g.
    MISTRANSLATION under ACCURACY) must NOT collide with any dimension's
    own mnemonic, dimension-level entries aside."""
    dimension_values = {d.value for d in MQMDimension}
    dimension_level_count = 0
    for error_type, dim in MQM_ERROR_TYPE_DIMENSION.items():
        if error_type.value == dim.value:
            dimension_level_count += 1
            continue
        assert error_type.value not in dimension_values, (
            f"subtype {error_type.value} collides with a dimension mnemonic"
        )
    assert dimension_level_count == len(MQMDimension)  # exactly one dimension-level entry each


def test_build_prompt_rubric_mentions_every_subtype_once():
    rubric = build_prompt_rubric()
    for error_type, dim in MQM_ERROR_TYPE_DIMENSION.items():
        if error_type.value == dim.value:
            continue  # dimension-level entries are the section headers, not listed as items
        assert error_type.value in rubric, f"{error_type.value} missing from rubric"


def test_score_error_accepts_neutral_severity_and_error_type():
    error = ScoreError(severity=ScoreErrorSeverity.NEUTRAL, count=1, error_type="term-inconsistency")
    assert error.severity == ScoreErrorSeverity.NEUTRAL
    assert error.error_type == "term-inconsistency"


class _HardFailStubScorer(QualityScorer):
    """Always scores well above any reasonable threshold, but flags
    hard_fail=True — isolates the hard-fail trigger from the numeric one."""

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        return ScoreResult(
            score=95, hard_fail=True,
            errors=[ScoreError(severity=ScoreErrorSeverity.CRITICAL, count=1, error_type="mistranslation")],
            reasons=["evaluator_flagged"],
        )


@pytest.mark.asyncio
async def test_redrive_engine_redrives_on_hard_fail_despite_high_score():
    await init_db()
    db = get_db()

    agent = await db.get_or_create_agent("test-hard-fail-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-hard-fail", source_text="Take 200mg maximum.", source_language="en-US",
        target_text="Take at least 200mg.", target_language="fr-FR",  # a critical meaning-reversal
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(
        scorer=_HardFailStubScorer(), scorer_label="hard-fail-stub", redrive_backend=MockTranslationBackend(),
    )
    # threshold=50 — the stub's score of 95 would normally SKIP this unit;
    # hard_fail must override that.
    run = RedriveRun(threshold=50, scope={"unit_ids": [unit.id]}, scoring_provider="hard-fail-stub", redrive_provider="mock")
    await db.create_redrive_run(run)
    completed = await engine.run(run)

    assert completed.summary["redriven"] == 1
    assert completed.summary["skipped_above_threshold"] == 0

    versions = await db.list_translation_unit_versions(unit.id)
    assert "hard_fail:critical_error" in (versions[-1].note or "")

    latest_quality = await db.get_latest_quality_score(unit.id)
    assert latest_quality.hard_fail is True


@pytest.mark.asyncio
async def test_quality_score_hard_fail_persists_through_repository():
    await init_db()
    db = get_db()
    from app.models.schemas import QualityScore

    agent = await db.get_or_create_agent("test-hard-fail-agent-2", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-hard-fail-2", source_text="Hello.", source_language="en-US",
        target_text="Bonjour.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    record = QualityScore(unit_id=unit.id, score=80, scorer="stub", hard_fail=True)
    await db.save_quality_score(record)

    latest = await db.get_latest_quality_score(unit.id)
    assert latest.hard_fail is True
    assert latest.score == 80
