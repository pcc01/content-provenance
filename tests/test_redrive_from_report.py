"""
Phase 3 — report-gated redrive: RedriveEngine.redrive_from_report() consumes
a saved QualityReport and routes each item (none / mt / human) to an engine
resolved per bucket / per unit. Reuses the marker scorer + unit helper from
tests/test_quality_reports.py.
Run with: PYTHONPATH=. pytest tests/test_redrive_from_report.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.redrive.engine import RedriveEngine, _resolve_routing_target
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.translation_backends import MockTranslationBackend
from app.models.schemas import (
    QualityReportBucket,
    QualityReportItem,
    RecommendedAction,
    RedriveRouting,
    RoutingTarget,
)
from tests.test_quality_reports import _MarkerScorer, _mk_unit


class _StubbornScorer(QualityScorer):
    """Never improves — any real translation scores 55. Exercises the Phase 4
    gate: an mt candidate that keeps failing the threshold is held, not
    applied."""

    async def score(self, unit):
        tgt = unit.target_text or ""
        if not tgt or tgt == unit.source_text:
            return ScoreResult(score=0, reasons=["untranslated"], deterministic=True)
        return ScoreResult(score=55, reasons=["evaluator_flagged"])


def _engine():
    return RedriveEngine(
        scorer=_MarkerScorer(), scorer_label="stub-judge",
        redrive_backend=MockTranslationBackend(), redrive_label="mock",
    )


async def _report_over(markers):
    db = get_db()
    units = [await _mk_unit(db, m) for m in markers]
    report = await _engine().evaluate(
        scope={"unit_ids": [u.id for u in units]}, quality_threshold=80,
    )
    return report, {u.id: m for u, m in zip(units, markers)}


# ── target resolution ──────────────────────────────────────────────────────

def _item(bucket, action, unit_id="u1", override=None):
    return QualityReportItem(
        report_id="r1", unit_id=unit_id, scorer="stub", bucket=bucket,
        recommended_action=action, route_override=override,
    )


def test_empty_routing_uses_the_item_default():
    t = _resolve_routing_target(RedriveRouting(), _item(QualityReportBucket.BELOW_QUALITY, RecommendedAction.MT))
    assert t.action == RecommendedAction.MT and t.provider is None


def test_by_bucket_overrides_default_and_sets_engine():
    routing = RedriveRouting(by_bucket={"hard_fail": RoutingTarget(action=RecommendedAction.MT, provider="deepl")})
    t = _resolve_routing_target(routing, _item(QualityReportBucket.HARD_FAIL, RecommendedAction.HUMAN))
    assert t.action == RecommendedAction.MT and t.provider == "deepl"


def test_route_override_changes_action_but_inherits_provider():
    routing = RedriveRouting(default=RoutingTarget(action=RecommendedAction.MT, provider="mock"))
    t = _resolve_routing_target(
        routing, _item(QualityReportBucket.BELOW_QUALITY, RecommendedAction.MT, override=RecommendedAction.HUMAN),
    )
    assert t.action == RecommendedAction.HUMAN and t.provider == "mock"


def test_by_unit_wins_over_route_override():
    routing = RedriveRouting(by_unit={"u1": RoutingTarget(action=RecommendedAction.MT, provider="mock")})
    t = _resolve_routing_target(
        routing, _item(QualityReportBucket.HARD_FAIL, RecommendedAction.HUMAN, override=RecommendedAction.HUMAN),
    )
    assert t.action == RecommendedAction.MT and t.provider == "mock"


# ── engine ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redrive_from_report_routes_by_default_recommendation():
    await init_db()
    report, by_id = await _report_over(["pass", "low", "critical", "unscoreable"])

    run = await _engine().redrive_from_report(report, RedriveRouting(), triggered_by="tester")

    assert run.from_report_id == report.id
    assert run.summary["redriven"] == 1           # the below_quality unit
    assert run.summary["pending_approval"] == 2   # hard_fail + needs_review
    assert run.summary["skipped_above_threshold"] == 1  # the pass unit

    by_unit = {it.unit_id: it for it in run.items}
    low_id = next(uid for uid, m in by_id.items() if m == "low")
    crit_id = next(uid for uid, m in by_id.items() if m == "critical")
    assert by_unit[low_id].outcome.value == "redriven"
    assert by_unit[crit_id].outcome.value == "pending_approval"
    assert by_unit[crit_id].proposed_text.startswith("[FR]")

    db = get_db()
    updated = await db.get_translation_unit(low_id)
    assert updated.target_text.startswith("[FR]")  # mt route applied immediately


@pytest.mark.asyncio
async def test_by_bucket_routes_hard_fail_to_mt():
    await init_db()
    report, by_id = await _report_over(["critical"])
    routing = RedriveRouting(by_bucket={"hard_fail": RoutingTarget(action=RecommendedAction.MT, provider="mock")})

    run = await _engine().redrive_from_report(report, routing)

    assert run.summary["redriven"] == 1
    assert run.summary["pending_approval"] == 0
    assert run.items[0].outcome.value == "redriven"
    assert "via mock (bucket=hard_fail)" in run.items[0].detail


@pytest.mark.asyncio
async def test_persisted_route_override_is_honoured():
    await init_db()
    db = get_db()
    report, by_id = await _report_over(["low"])
    item_id = report.items[0].id

    await db.set_quality_report_item_route_override(item_id, RecommendedAction.HUMAN)
    fresh = await db.get_quality_report(report.id)

    run = await _engine().redrive_from_report(fresh, RedriveRouting())
    assert run.summary["pending_approval"] == 1
    assert run.items[0].outcome.value == "pending_approval"


# ── API ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redrive_runs_from_report_id(client, monkeypatch):
    await init_db()
    db = get_db()
    monkeypatch.setattr(
        "app.api.quality_reports.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )
    monkeypatch.setattr(
        "app.api.redrive.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )
    units = [await _mk_unit(db, m) for m in ("low", "critical")]
    rep = await client.post("/api/v1/quality/reports", json={
        "scope": {"unit_ids": [u.id for u in units]}, "threshold": 80, "scoring_provider": "stub-judge",
    })
    report_id = rep.json()["id"]

    run_resp = await client.post("/api/v1/redrive/runs", json={
        "from_report_id": report_id,
        "routing": {"default": {"action": "mt", "provider": "mock"}},
        "triggered_by": "tester",
    })
    assert run_resp.status_code == 200
    run = run_resp.json()
    assert run["from_report_id"] == report_id
    assert run["summary"]["redriven"] == 2  # default mt for both
    assert run["routing"]["default"]["provider"] == "mock"


@pytest.mark.asyncio
async def test_redrive_runs_from_missing_report_404(client):
    resp = await client.post("/api/v1/redrive/runs", json={"from_report_id": "nope"})
    assert resp.status_code == 404


# ── Phase 4: second-pass gate ──────────────────────────────────────────────

def _stubborn_engine():
    return RedriveEngine(
        scorer=_StubbornScorer(), scorer_label="stubborn",
        redrive_backend=MockTranslationBackend(), redrive_label="mock",
    )


@pytest.mark.asyncio
async def test_failed_second_pass_holds_the_candidate_instead_of_applying():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _stubborn_engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)
    original_target = (await db.get_translation_unit(unit.id)).target_text

    run = await _stubborn_engine().redrive_from_report(
        report, RedriveRouting(default=RoutingTarget(action=RecommendedAction.MT, provider="mock")),
    )

    assert run.summary["redriven"] == 0
    assert run.summary["pending_approval"] == 1
    item = run.items[0]
    assert item.outcome.value == "pending_approval"
    assert item.proposed_text.startswith("[FR]")
    assert "second-pass score 55" in item.detail
    # the previous version is untouched — a failed retranslation never goes live
    assert (await db.get_translation_unit(unit.id)).target_text == original_target


@pytest.mark.asyncio
async def test_passing_second_pass_applies_immediately():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    run = await _engine().redrive_from_report(
        report, RedriveRouting(default=RoutingTarget(action=RecommendedAction.MT, provider="mock")),
    )

    assert run.summary["redriven"] == 1
    assert run.items[0].outcome.value == "redriven"
    assert (await db.get_translation_unit(unit.id)).target_text.startswith("[FR]")


@pytest.mark.asyncio
async def test_version_note_names_the_per_bucket_engine_not_the_run_default():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    engine = RedriveEngine(
        scorer=_MarkerScorer(), scorer_label="stub-judge",
        redrive_backend=MockTranslationBackend(), redrive_label="run-default-label",
    )
    await engine.redrive_from_report(
        report,
        RedriveRouting(by_bucket={"below_quality": RoutingTarget(action=RecommendedAction.MT, provider="mock")}),
    )

    versions = await db.list_translation_unit_versions(unit.id)
    assert "Redriven via mock" in (versions[-1].note or "")
    assert "run-default-label" not in (versions[-1].note or "")


@pytest.mark.asyncio
async def test_approving_a_report_item_keeps_the_drafting_engine_in_provenance():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "critical")  # hard_fail -> human route
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    engine = RedriveEngine(
        scorer=_MarkerScorer(), scorer_label="stub-judge",
        redrive_backend=MockTranslationBackend(), redrive_label="run-default-label",
    )
    run = await engine.redrive_from_report(
        report,
        RedriveRouting(by_bucket={"hard_fail": RoutingTarget(action=RecommendedAction.HUMAN, provider="mock")}),
    )
    pending = run.items[0]
    assert pending.outcome.value == "pending_approval"

    approved = await engine.approve_item(pending.id, approved_by="rev@x.com")
    assert "drafted via mock" in approved.detail

    versions = await db.list_translation_unit_versions(unit.id)
    assert "Redriven via mock" in (versions[-1].note or "")
    assert "approved by rev@x.com" in (versions[-1].note or "")


@pytest.mark.asyncio
async def test_second_review_holds_even_a_passing_candidate():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)

    run = await _engine().redrive_from_report(
        report, RedriveRouting(default=RoutingTarget(action=RecommendedAction.MT, provider="mock")),
        second_review=True,
    )

    assert run.second_review is True
    assert run.summary["redriven"] == 0
    assert run.summary["pending_approval"] == 1
    assert "second-review requested" in run.items[0].detail
    assert (await db.get_translation_unit(unit.id)).target_text != run.items[0].proposed_text
