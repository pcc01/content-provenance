"""Tests for Phase 15's non-LLM automatic metrics — METEOR (fully
exercised, nltk is installed) and COMET-Kiwi (wiring/graceful-degradation
only — no model download in this environment, same convention as
ClaudeQualityScorer's untested live API call). See
app/core/scoring/automatic/.
Run with: PYTHONPATH=. pytest tests/test_automatic_metrics.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.automatic.comet_kiwi import comet_kiwi_available, score_comet_kiwi_batch
from app.core.scoring.automatic.meteor import compute_meteor, meteor_available
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.translation_backends import MockTranslationBackend
from app.models.schemas import AutomaticMetricScore, RedriveRun, TranslationMethod, TranslationUnit


class _AlwaysBadStubScorer(QualityScorer):
    async def score(self, unit: TranslationUnit) -> ScoreResult:
        return ScoreResult(score=0, reasons=["untranslated"], deterministic=True)


# ── METEOR ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_meteor_scores_identical_text_near_perfect():
    assert meteor_available()
    score = await compute_meteor("Bienvenue sur notre plateforme", "Bienvenue sur notre plateforme")
    assert score > 95


@pytest.mark.asyncio
async def test_meteor_scores_unrelated_text_much_lower():
    identical = await compute_meteor("Bienvenue sur notre plateforme", "Bienvenue sur notre plateforme")
    unrelated = await compute_meteor("Salut la plateforme", "Bienvenue sur notre plateforme")
    assert unrelated < identical


@pytest.mark.asyncio
async def test_meteor_returns_none_for_empty_input():
    assert await compute_meteor("", "something") is None
    assert await compute_meteor("something", "") is None


@pytest.mark.asyncio
async def test_repository_round_trips_automatic_metric_score():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("automatic-metric-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-automatic-1", source_text="Hello.", source_language="en-US",
        target_text="Bonjour.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    await db.save_automatic_metric_score(AutomaticMetricScore(
        unit_id=unit.id, metric="meteor", score=88.5, raw_score=0.885,
        reference_type="previous_version",
    ))
    latest = await db.get_latest_automatic_metric_score(unit.id, "meteor")
    assert latest.score == 88.5
    assert latest.reference_type == "previous_version"

    # A different metric on the same unit doesn't collide.
    assert await db.get_latest_automatic_metric_score(unit.id, "comet_kiwi") is None


@pytest.mark.asyncio
async def test_redrive_engine_records_meteor_regression_score():
    """Integration: a real redrive through RedriveEngine must leave behind
    a "meteor" automatic_metric_scores row comparing the new text against
    the version it replaced — app/core/redrive/engine.py's
    _record_meteor_regression, called from _apply_redrive."""
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("automatic-metric-redrive-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-automatic-2", source_text="Needs a real translation.", source_language="en-US",
        target_text="Needs a real translation.", target_language="fr-FR",  # untranslated, will redrive
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(
        scorer=_AlwaysBadStubScorer(), scorer_label="stub", redrive_backend=MockTranslationBackend(),
    )
    run = RedriveRun(threshold=50, scope={"unit_ids": [unit.id]}, scoring_provider="stub", redrive_provider="mock")
    await db.create_redrive_run(run)
    completed = await engine.run(run)
    assert completed.summary["redriven"] == 1

    meteor_record = await db.get_latest_automatic_metric_score(unit.id, "meteor")
    assert meteor_record is not None
    assert meteor_record.reference_type == "previous_version"
    assert meteor_record.score is not None


# ── COMET-Kiwi (wiring only) ────────────────────────────────────────────

def test_comet_kiwi_reports_unavailable_when_package_missing():
    """unbabel-comet is intentionally NOT installed in this environment —
    see comet_kiwi.py's module docstring for why."""
    assert comet_kiwi_available() is False


@pytest.mark.asyncio
async def test_comet_kiwi_batch_degrades_gracefully_without_model():
    agent_unit = TranslationUnit(
        source_id="src-comet-1", source_text="Hello.", source_language="en-US",
        target_text="Bonjour.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id="agent:x",
    )
    results = await score_comet_kiwi_batch([agent_unit])
    assert results == [None]


@pytest.mark.asyncio
async def test_comet_score_api_returns_503_when_unavailable(client):
    r = await client.post("/api/v1/quality/comet-score", json={"unit_ids": ["does-not-matter"]})
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_meteor_compare_api(client):
    r = await client.post("/api/v1/quality/meteor-compare", json={
        "hypothesis": "Bienvenue sur notre plateforme", "reference": "Bienvenue sur notre plateforme",
    })
    assert r.status_code == 200
    assert r.json()["score"] > 95
