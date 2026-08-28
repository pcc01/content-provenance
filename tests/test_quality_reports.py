"""
Tests for the Quality Report step (report-gated redrive, Phase 1/2):
RedriveEngine.evaluate() buckets + totals, the /quality/reports API,
JSON + PDF export, and per-unit route overrides.
Run with: PYTHONPATH=. pytest tests/test_quality_reports.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.base import QualityScorer, ScoreResult
from app.models.schemas import (
    RecommendedAction,
    ScoreError,
    ScoreErrorSeverity,
    TranslationMethod,
    TranslationUnit,
)


_MOCK_PREFIXES = tuple(f"[{c}]" for c in ("FR", "DE", "ES", "JA", "ZH", "PT", "IT", "KO", "AR", "NL"))


class _MarkerScorer(QualityScorer):
    """Buckets a unit by a marker in its source text — deterministic/offline
    so these tests don't need a real judge. `pass` -> 95, `low` -> 40,
    `critical` -> 88 + hard_fail, `unscoreable` -> None/needs_review. A target
    carrying a MockTranslationBackend prefix (`[FR] …`) is treated as a
    landed retranslation and scores 95 — so the Phase 4 second-pass gate
    sees an mt candidate that actually cleared the bar."""

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        src = unit.source_text.lower()
        tgt = unit.target_text or ""
        if not tgt or tgt == unit.source_text:
            # what CompositeScorer's deterministic pre-check would resolve
            return ScoreResult(score=0, reasons=["untranslated"], deterministic=True)
        if tgt.startswith(_MOCK_PREFIXES):
            return ScoreResult(score=95)
        if "critical" in src:
            return ScoreResult(
                score=88, hard_fail=True, reasons=["evaluator_flagged"],
                errors=[ScoreError(severity=ScoreErrorSeverity.CRITICAL, count=1, error_type="mistranslation")],
            )
        if "unscoreable" in src:
            return ScoreResult(score=None, reasons=["evaluator_error"], needs_review=True)
        if "low" in src:
            return ScoreResult(score=40, reasons=["evaluator_flagged"])
        return ScoreResult(score=95)


async def _mk_unit(db, marker: str) -> TranslationUnit:
    agent = await db.get_or_create_agent("qr-test-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id=f"qr-{marker}", source_text=f"This segment is {marker}.", source_language="en-US",
        target_text=f"Ce segment est {marker}.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)
    return unit


@pytest.mark.asyncio
async def test_evaluate_buckets_units_and_persists_report():
    await init_db()
    db = get_db()
    units = [await _mk_unit(db, m) for m in ("pass", "low", "critical", "unscoreable")]
    scope = {"unit_ids": [u.id for u in units]}

    engine = RedriveEngine(scorer=_MarkerScorer(), scorer_label="stub-judge")
    report = await engine.evaluate(scope=scope, quality_threshold=80)

    assert report.status.value == "completed"
    assert report.totals["units"] == 4
    assert report.summary["pass"] == 1
    assert report.summary["below_quality"] == 1
    assert report.summary["hard_fail"] == 1
    assert report.summary["needs_review"] == 1
    assert report.totals["below_threshold"] == 2  # below_quality + hard_fail

    by_unit = {it.unit_id: it for it in report.items}
    assert by_unit[units[0].id].bucket.value == "pass"
    assert by_unit[units[0].id].recommended_action == RecommendedAction.NONE
    assert by_unit[units[1].id].bucket.value == "below_quality"
    assert by_unit[units[1].id].recommended_action == RecommendedAction.MT
    assert by_unit[units[2].id].bucket.value == "hard_fail"
    assert by_unit[units[2].id].recommended_action == RecommendedAction.HUMAN
    assert by_unit[units[2].id].hard_fail is True
    assert by_unit[units[3].id].bucket.value == "needs_review"
    assert by_unit[units[3].id].recommended_action == RecommendedAction.HUMAN

    # each item points at a persisted QualityScore row
    for it in report.items:
        assert it.quality_score_id


@pytest.mark.asyncio
async def test_evaluate_flags_non_commercial_signal_for_mprometheus():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    engine = RedriveEngine(scorer=_MarkerScorer(), scorer_label="mprometheus")
    report = await engine.evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    assert report.items[0].commercial_safe is False
    assert report.totals["non_commercial"] == 1
    assert report.totals["commercial_safe"] == 0


@pytest.mark.asyncio
async def test_evaluate_marks_deterministic_floor_as_commercial_safe():
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("qr-det-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="qr-det", source_text="Untouched segment here.", source_language="en-US",
        target_text="Untouched segment here.", target_language="fr-FR",  # untranslated -> deterministic floor
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    engine = RedriveEngine(scorer=_MarkerScorer(), scorer_label="mprometheus")
    report = await engine.evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    it = report.items[0]
    assert it.scorer == "deterministic"
    assert it.commercial_safe is True
    assert it.bucket.value == "below_quality"  # score 0 from the free check


# ── API ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reports_api_create_get_and_exports(client, monkeypatch):
    await init_db()
    db = get_db()
    units = [await _mk_unit(db, m) for m in ("pass", "low", "critical")]

    monkeypatch.setattr(
        "app.api.quality_reports.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )

    resp = await client.post("/api/v1/quality/reports", json={
        "scope": {"unit_ids": [u.id for u in units]}, "threshold": 80,
        "scoring_provider": "stub-judge", "triggered_by": "tester",
    })
    assert resp.status_code == 200
    report = resp.json()
    assert report["status"] == "completed"
    assert len(report["items"]) == 3
    report_id = report["id"]

    got = await client.get(f"/api/v1/quality/reports/{report_id}")
    assert got.status_code == 200
    assert got.json()["totals"]["below_threshold"] == 2

    j = await client.get(f"/api/v1/quality/reports/{report_id}/export.json")
    assert j.status_code == 200
    assert "attachment" in j.headers["content-disposition"]
    assert len(j.json()["items"]) == 3

    p = await client.get(f"/api/v1/quality/reports/{report_id}/export.pdf")
    assert p.status_code == 200
    assert p.headers["content-type"] == "application/pdf"
    assert p.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_report_item_route_override(client, monkeypatch):
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    monkeypatch.setattr(
        "app.api.quality_reports.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )
    resp = await client.post("/api/v1/quality/reports", json={
        "scope": {"unit_ids": [unit.id]}, "threshold": 80, "scoring_provider": "stub-judge",
    })
    report = resp.json()
    item_id = report["items"][0]["id"]
    assert report["items"][0]["recommended_action"] == "mt"
    assert report["items"][0]["route_override"] is None

    patched = await client.patch(
        f"/api/v1/quality/reports/{report['id']}/items/{item_id}", json={"action": "human"},
    )
    assert patched.status_code == 200
    assert patched.json()["route_override"] == "human"

    cleared = await client.patch(
        f"/api/v1/quality/reports/{report['id']}/items/{item_id}", json={"action": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["route_override"] is None


@pytest.mark.asyncio
async def test_get_report_404(client):
    resp = await client.get("/api/v1/quality/reports/does-not-exist")
    assert resp.status_code == 404
