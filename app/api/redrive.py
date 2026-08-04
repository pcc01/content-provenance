"""
Threshold-quality redrive API — score, threshold, and redrive translation
units through the configured scorer/backend.

POST /api/v1/redrive/runs                              - create + run a redrive pass
GET  /api/v1/redrive/runs/{id}                         - status/results of a run
POST /api/v1/redrive/runs/{id}/items/{item_id}/approve - human-in-the-loop: apply a proposed redrive
POST /api/v1/redrive/runs/{id}/items/{item_id}/reject  - human-in-the-loop: decline a proposed redrive
POST /api/v1/redrive/propose                           - Phase 10: a human proposes their own translation, goes through the same approval
GET  /api/v1/redrive/preview                           - dry-run forecast (no writes to translations, no redrive spend)
GET  /api/v1/redrive/queue                             - units currently below a threshold, worst-first
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.redrive.engine import RedriveEngine
from app.core.redrive.propose import propose_human_translation
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.factory import get_scorer
from app.models.schemas import RedriveRun, RedriveRunItem, TranslationUnit

router = APIRouter()


class _NeverInvokedScorer(QualityScorer):
    """approve_item/reject_item never call .score() — RedriveEngine still
    requires a scorer instance at construction time, and "human" (Phase
    10's proposal runs) isn't a real provider get_scorer() recognizes. This
    exists purely so construction succeeds; if it were ever actually
    invoked that's a bug elsewhere, so it fails loudly rather than
    returning a made-up score."""

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        raise RuntimeError("_NeverInvokedScorer.score() was called — this should be unreachable.")


class RedriveRunRequest(BaseModel):
    threshold: float = Field(80, ge=0, le=100)
    scope: Dict[str, Any] = Field(default_factory=dict)
    scoring_provider: Optional[str] = None  # defaults to settings.scoring_provider
    require_human_approval: bool = False
    triggered_by: Optional[str] = None


class RedriveApprovalRequest(BaseModel):
    actor: str  # who approved/rejected — reviewer name/email/id
    reason: Optional[str] = None  # only meaningful for reject


class ProposeRequest(BaseModel):
    unit_id: str
    proposed_text: str
    proposed_by: str


def _build_engine(scoring_provider: Optional[str], redrive_label: Optional[str] = None) -> RedriveEngine:
    provider = (scoring_provider or settings.scoring_provider).lower()
    scorer = _NeverInvokedScorer() if provider == "human" else get_scorer(provider)
    return RedriveEngine(scorer=scorer, scorer_label=provider, redrive_label=redrive_label)


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
    engine = _build_engine(run.scoring_provider, redrive_label=run.redrive_provider)
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
    engine = _build_engine(run.scoring_provider, redrive_label=run.redrive_provider)
    try:
        return await engine.reject_item(item_id, rejected_by=request.actor, reason=request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/propose", response_model=RedriveRunItem, status_code=201)
async def propose_redrive(request: ProposeRequest):
    """Phase 10: a human reviewer's own typed draft, not a scorer-triggered
    redrive — creates a single-item ad-hoc RedriveRun so the exact same
    approve/reject endpoints above apply to it unchanged."""
    try:
        return await propose_human_translation(request.unit_id, request.proposed_text, request.proposed_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
