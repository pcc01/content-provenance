"""Phase 6 — XCOMET error spans attached to a Quality Report. XCOMET itself
(unbabel-comet) is NOT installed in CI, same as COMET-Kiwi — the real model
path is covered by graceful-degradation checks; the attach flow is covered
with a monkeypatched score_xcomet_batch.
Run with: PYTHONPATH=. pytest tests/test_xcomet.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.scoring.automatic.xcomet import score_xcomet_batch, xcomet_available
from tests.test_quality_reports import _MarkerScorer, _mk_unit
from tests.test_redrive_from_report import _engine


def test_xcomet_reports_unavailable_when_package_missing():
    assert xcomet_available() is False


@pytest.mark.asyncio
async def test_score_xcomet_batch_degrades_to_none_without_model():
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    assert await score_xcomet_batch([unit]) == [None]


@pytest.mark.asyncio
async def test_attach_xcomet_api_503_when_unavailable(client):
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)
    resp = await client.post(f"/api/v1/quality/reports/{report.id}/attach-xcomet")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_attach_xcomet_writes_spans_and_flips_commercial_flag(client, monkeypatch):
    await init_db()
    db = get_db()
    units = [await _mk_unit(db, m) for m in ("low", "critical")]
    # evaluate with a commercial-safe judge so we can see the flag flip
    monkeypatch.setattr(
        "app.api.quality_reports.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )
    rep = await client.post("/api/v1/quality/reports", json={
        "scope": {"unit_ids": [u.id for u in units]}, "threshold": 80, "scoring_provider": "claude",
    })
    report = rep.json()
    assert all(it["commercial_safe"] is True for it in report["items"])
    assert all(it["error_spans"] == [] for it in report["items"])

    monkeypatch.setattr("app.api.quality_reports.xcomet_available", lambda: True)

    async def _fake_batch(units, gpus=0):
        return [
            {"score": 0.42, "spans": [{"text": "low", "severity": "major", "start": 16, "end": 19}]}
            for _ in units
        ]

    monkeypatch.setattr("app.api.quality_reports.score_xcomet_batch", _fake_batch)

    attached = await client.post(f"/api/v1/quality/reports/{report['id']}/attach-xcomet")
    assert attached.status_code == 200
    body = attached.json()
    assert all(len(it["error_spans"]) == 1 for it in body["items"])
    assert body["items"][0]["error_spans"][0]["severity"] == "major"
    assert all(it["commercial_safe"] is False for it in body["items"])
    assert body["totals"]["non_commercial"] == 2
    assert body["totals"]["commercial_safe"] == 0

    # an xcomet AutomaticMetricScore row was written per unit
    for u in units:
        latest = await db.get_latest_automatic_metric_score(u.id, "xcomet")
        assert latest is not None and latest.raw_score == 0.42


@pytest.mark.asyncio
async def test_attach_cometkiwi_wordtags_coexist_with_xcomet_spans(client, monkeypatch):
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    monkeypatch.setattr(
        "app.api.quality_reports.get_scorer",
        lambda provider=None, model=None, reference_mode=None: _MarkerScorer(),
    )
    rep = await client.post("/api/v1/quality/reports", json={
        "scope": {"unit_ids": [unit.id]}, "threshold": 80, "scoring_provider": "claude",
    })
    report_id = rep.json()["id"]

    monkeypatch.setattr("app.api.quality_reports.xcomet_available", lambda: True)
    monkeypatch.setattr("app.api.quality_reports.qe_wordlevel_available", lambda: True)

    async def _xc(units, gpus=0):
        return [{"score": 0.4, "spans": [{"text": "a", "severity": "critical", "start": 0, "end": 1}]} for _ in units]

    async def _kiwi(units, gpus=0):
        return [{"score": 0.5, "spans": [{"text": "b", "severity": "major", "start": 2, "end": 3}]} for _ in units]

    monkeypatch.setattr("app.api.quality_reports.score_xcomet_batch", _xc)
    monkeypatch.setattr("app.api.quality_reports.score_cometkiwi_wordlevel_batch", _kiwi)

    await client.post(f"/api/v1/quality/reports/{report_id}/attach-xcomet")
    after = await client.post(f"/api/v1/quality/reports/{report_id}/attach-cometkiwi")
    spans = after.json()["items"][0]["error_spans"]
    sources = sorted(s["source"] for s in spans)
    assert sources == ["cometkiwi", "xcomet"]

    # re-running xcomet replaces only its own spans, keeps cometkiwi's
    again = await client.post(f"/api/v1/quality/reports/{report_id}/attach-xcomet")
    spans2 = again.json()["items"][0]["error_spans"]
    assert sorted(s["source"] for s in spans2) == ["cometkiwi", "xcomet"]


@pytest.mark.asyncio
async def test_attach_cometkiwi_503_when_unavailable(client):
    await init_db()
    db = get_db()
    unit = await _mk_unit(db, "low")
    report = await _engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)
    resp = await client.post(f"/api/v1/quality/reports/{report.id}/attach-cometkiwi")
    assert resp.status_code == 503
