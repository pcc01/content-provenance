"""
Quality Reports API — the "produce a report with quality issues" step that
sits between evaluate and redrive (report-gated redrive plan, Phase 1/2).

POST /api/v1/quality/reports                         - run an evaluate pass, persist a report
GET  /api/v1/quality/reports                         - recent reports (no items)
GET  /api/v1/quality/reports/{id}                    - one report with its per-unit items
GET  /api/v1/quality/reports/{id}/export.json       - the same, as a JSON download
GET  /api/v1/quality/reports/{id}/export.pdf        - branded PDF (issues worst-first)
PATCH /api/v1/quality/reports/{id}/items/{item_id}  - override one unit's route (human|mt|none)

Spends no translation budget — Phase 3's redrive consumes a saved report
instead of re-scoring.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.quality_report_pdf import generate_quality_report_pdf
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.automatic.qe_wordlevel import (
    qe_wordlevel_available,
    score_cometkiwi_wordlevel_batch,
)
from app.core.scoring.automatic.xcomet import score_xcomet_batch, xcomet_available
from app.core.scoring.factory import get_scorer
from app.models.schemas import (
    AutomaticMetricScore,
    QualityReport,
    QualityReportItem,
    RecommendedAction,
)

router = APIRouter()


class QualityReportRequest(BaseModel):
    scope: Dict[str, Any] = Field(default_factory=dict)  # target_language / source_language / unit_ids / status / limit
    threshold: float = Field(80, ge=0, le=100)
    style_threshold: Optional[float] = Field(None, ge=0, le=100)
    style_guide_id: Optional[str] = None
    # "claude" | "ollama" | "mprometheus" | "openai" | "gemini" | "lmstudio" | "vllm"
    scoring_provider: Optional[str] = None
    scoring_model: Optional[str] = None
    reference_mode: Optional[str] = None  # mprometheus only
    triggered_by: Optional[str] = None


class RouteOverrideRequest(BaseModel):
    action: Optional[RecommendedAction] = None  # null clears the override (fall back to the bucket default)


def _build_engine(
    scoring_provider: Optional[str], scoring_model: Optional[str], reference_mode: Optional[str],
) -> RedriveEngine:
    provider = (scoring_provider or settings.scoring_provider).lower()
    scorer = get_scorer(provider, scoring_model, reference_mode)
    return RedriveEngine(scorer=scorer, scorer_label=provider)


@router.post("/reports", response_model=QualityReport)
async def create_quality_report(request: QualityReportRequest):
    """Runs synchronously and returns the completed report — same contract
    shape as POST /redrive/runs."""
    try:
        engine = _build_engine(request.scoring_provider, request.scoring_model, request.reference_mode)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await engine.evaluate(
        scope=request.scope, quality_threshold=request.threshold,
        style_threshold=request.style_threshold, style_guide_id=request.style_guide_id,
        scoring_model=request.scoring_model, reference_mode=request.reference_mode,
        triggered_by=request.triggered_by,
    )


@router.get("/reports")
async def list_quality_reports(limit: int = 25):
    db = get_db()
    reports = await db.list_quality_reports(limit=limit)
    return [r.model_dump(mode="json") for r in reports]


@router.get("/reports/{report_id}", response_model=QualityReport)
async def get_quality_report(report_id: str):
    db = get_db()
    report = await db.get_quality_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report {report_id} not found")
    return report


@router.get("/reports/{report_id}/export.json")
async def export_quality_report_json(report_id: str):
    db = get_db()
    report = await db.get_quality_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report {report_id} not found")
    return JSONResponse(
        content=report.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="quality-report-{report_id}.json"'},
    )


@router.get("/reports/{report_id}/export.pdf")
async def export_quality_report_pdf(report_id: str):
    db = get_db()
    report = await db.get_quality_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report {report_id} not found")
    pdf = generate_quality_report_pdf(report, report.items)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="quality-report-{report_id}.pdf"'},
    )


async def _attach_spans(report_id: str, source: str, metric: str, score_fn, checkpoint: str):
    """Shared body for attach-xcomet / attach-cometkiwi: batch-score the
    report's units, merge the span set for `source` onto each item, write an
    AutomaticMetricScore, re-mark touched items non-commercial, recompute the
    report's commercial totals."""
    db = get_db()
    report = await db.get_quality_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report {report_id} not found")

    units = [await db.get_translation_unit(it.unit_id) for it in report.items]
    results = await score_fn([u for u in units if u is not None])

    result_iter = iter(results)
    for item, unit in zip(report.items, units):
        if unit is None:
            continue
        r = next(result_iter, None)
        if r is None:
            continue
        await db.merge_quality_report_item_error_spans(item.id, source, r["spans"])
        await db.save_automatic_metric_score(AutomaticMetricScore(
            unit_id=item.unit_id, metric=metric,
            score=round(r["score"] * 100, 2), raw_score=r["score"],
            detail={"checkpoint": checkpoint, "spans": r["spans"]},
        ))

    refreshed = await db.get_quality_report(report_id)
    safe = sum(1 for it in refreshed.items if it.commercial_safe is True)
    noncomm = sum(1 for it in refreshed.items if it.commercial_safe is False)
    unknown = sum(1 for it in refreshed.items if it.commercial_safe is None)
    await db.update_quality_report(report_id, totals={
        **refreshed.totals,
        "commercial_safe": safe, "non_commercial": noncomm, "commercial_unknown": unknown,
    })
    return await db.get_quality_report(report_id)


@router.post("/reports/{report_id}/attach-xcomet", response_model=QualityReport)
async def attach_xcomet_spans(report_id: str):
    """Phase 6 — run XCOMET over the report's units and attach localized error
    spans (`minor`/`major`/`critical` + char offsets). Batch/offline,
    non-commercial (CC-BY-NC-SA-4.0). 503 if unbabel-comet / the checkpoint
    isn't available (see app/core/scoring/automatic/xcomet.py)."""
    if not xcomet_available():
        raise HTTPException(
            status_code=503,
            detail="unbabel-comet not installed, or the XCOMET checkpoint isn't downloaded.",
        )
    return await _attach_spans(report_id, "xcomet", "xcomet", score_xcomet_batch, "Unbabel/XCOMET-XL")


@router.post("/reports/{report_id}/attach-cometkiwi", response_model=QualityReport)
async def attach_cometkiwi_wordtags(report_id: str):
    """Phase 6 follow-up — attach CometKiwi word-level BAD tokens as
    major-severity spans. Same non-commercial posture as XCOMET; 503 when
    unbabel-comet / the word-level checkpoint isn't available."""
    if not qe_wordlevel_available():
        raise HTTPException(
            status_code=503,
            detail="unbabel-comet not installed, or the word-level QE checkpoint isn't downloaded.",
        )
    return await _attach_spans(
        report_id, "cometkiwi", "comet_kiwi",
        score_cometkiwi_wordlevel_batch, "Unbabel/WMT24-QE-task2-baseline",
    )


@router.patch("/reports/{report_id}/items/{item_id}", response_model=QualityReportItem)
async def override_item_route(report_id: str, item_id: str, request: RouteOverrideRequest):
    """A reviewer re-routes one unit before the redrive — e.g. send a
    below-quality unit to a human instead of MT, or vice versa. Phase 3's
    redrive_from_report honours route_override ahead of the bucket default."""
    db = get_db()
    updated = await db.set_quality_report_item_route_override(item_id, request.action)
    if updated is None or updated.report_id != report_id:
        raise HTTPException(status_code=404, detail=f"Report item {item_id} not found in report {report_id}")
    return updated
