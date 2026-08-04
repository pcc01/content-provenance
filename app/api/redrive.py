"""
Threshold-quality redrive API — score, threshold, and redrive translation
units through the configured scorer/backend.

POST /api/v1/redrive/runs                              - create + run a redrive pass
GET  /api/v1/redrive/runs/{id}                         - status/results of a run
POST /api/v1/redrive/runs/{id}/items/{item_id}/approve - human-in-the-loop: apply a proposed redrive
POST /api/v1/redrive/runs/{id}/items/{item_id}/reject  - human-in-the-loop: decline a proposed redrive
GET  /api/v1/redrive/preview                           - dry-run forecast (no writes to translations, no redrive spend)
GET  /api/v1/redrive/queue                             - units currently below a threshold, worst-first
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.redrive.engine import RedriveEngine
from app.core.scoring.factory import get_scorer
from app.models.schemas import RedriveRun, RedriveRunItem

router = APIRouter()


class RedriveRunRequest(BaseModel):
    threshold: float = Field(80, ge=0, le=100)
    scope: Dict[str, Any] = Field(default_factory=dict)
    scoring_provider: Optional[str] = None  # defaults to settings.scoring_provider
    require_human_approval: bool = False
    triggered_by: Optional[str] = None


class RedriveApprovalRequest(BaseModel):
    actor: str  # who approved/rejected — reviewer name/email/id
    reason: Optional[str] = None  # only meaningful for reject


def _build_engine(scoring_provider: Optional[str]) -> RedriveEngine:
    provider = (scoring_provider or settings.scoring_provider).lower()
    scorer = get_scorer(provider)
    return RedriveEngine(scorer=scorer, scorer_label=provider)


@router.post("/runs", response_model=RedriveRun)
async def create_redrive_run(request: RedriveRunRequest):
    """Runs synchronously and returns the completed run — GET /runs/{id}
    still exists for polling, so a future background-task version of this
    endpoint can change how the run executes without changing the contract.

    When require_human_approval is set, below-threshold units come back with
    outcome="pending_approval" and a proposed_text instead of being applied —
    call the approve/reject endpoints below to resolve each one."""
    db = get_db()
    engine = _build_engine(request.scoring_provider)

    run = RedriveRun(
        threshold=request.threshold, scope=request.scope,
        scoring_provider=engine.scorer_label, redrive_provider=engine.redrive_label,
        require_human_approval=request.require_human_approval,
        triggered_by=request.triggered_by,
    )
    await db.create_redrive_run(run)
    return await engine.run(run)


@router.get("/runs/{run_id}", response_model=RedriveRun)
async def get_redrive_run(run_id: str):
    db = get_db()
    run = await db.get_redrive_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Redrive run {run_id} not found")
    return run


@router.post("/runs/{run_id}/items/{item_id}/approve", response_model=RedriveRunItem)
async def approve_redrive_item(run_id: str, item_id: str, request: RedriveApprovalRequest):
    db = get_db()
    run = await db.get_redrive_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Redrive run {run_id} not found")
    engine = _build_engine(run.scoring_provider)
    try:
        return await engine.approve_item(item_id, approved_by=request.actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/items/{item_id}/reject", response_model=RedriveRunItem)
async def reject_redrive_item(run_id: str, item_id: str, request: RedriveApprovalRequest):
    db = get_db()
    run = await db.get_redrive_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Redrive run {run_id} not found")
    engine = _build_engine(run.scoring_provider)
    try:
        return await engine.reject_item(item_id, rejected_by=request.actor, reason=request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preview")
async def preview_redrive(
    threshold: float = 80,
    target_language: Optional[str] = None,
    source_language: Optional[str] = None,
    scoring_provider: Optional[str] = None,
):
    """Scores everything in scope and reports how many units this threshold
    would catch — same 'how many keys each cutoff would send' idea as
    peripateticware's show_report_summary, without spending redrive budget."""
    scope: Dict[str, Any] = {}
    if target_language:
        scope["target_language"] = target_language
    if source_language:
        scope["source_language"] = source_language
    engine = _build_engine(scoring_provider)
    return await engine.preview(scope, threshold)


@router.get("/queue")
async def redrive_queue(threshold: float = 80, target_language: Optional[str] = None, limit: int = 50):
    """Units whose latest quality score is below `threshold` — the review
    UI's worklist (worst-first), the same UX peripateticware's ranked report
    gives reviewers. Only reflects scores already on record; run /preview or
    a redrive run first to (re)score a scope that hasn't been assessed yet."""
    db = get_db()
    scope: Dict[str, Any] = {"limit": limit}
    if target_language:
        scope["target_language"] = target_language
    units = await db.list_units_by_scope(scope)

    queue = []
    for unit in units:
        latest = await db.get_latest_quality_score(unit.id)
        if latest is not None and latest.score is not None and latest.score < threshold:
            queue.append({
                "unit_id": unit.id, "score": latest.score, "reasons": latest.reasons,
                "source_text": unit.source_text, "target_text": unit.target_text,
                "target_language": unit.target_language, "scored_at": latest.scored_at.isoformat(),
            })
    queue.sort(key=lambda item: item["score"])
    return queue
