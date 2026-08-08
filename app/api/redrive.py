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

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.redrive.engine import RedriveEngine, _NeverInvokedScorer, build_engine_for_item
from app.core.redrive.propose import propose_human_translation
from app.core.scoring.factory import get_scorer
from app.core.translation_backends import get_translation_backend
from app.models.schemas import RedriveRun, RedriveRunItem

router = APIRouter()


class RedriveRunRequest(BaseModel):
    threshold: float = Field(80, ge=0, le=100)
    # Phase 13 — independent style-adherence threshold axis; None (default)
    # means style is never itself a reason to redrive. See
    # RedriveRun.style_threshold's docstring.
    style_threshold: Optional[float] = Field(None, ge=0, le=100)
    style_guide_id: Optional[str] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    scoring_provider: Optional[str] = None  # defaults to settings.scoring_provider — the "evaluate" model
    # Phase 16 — which model actually REtranslates a below-threshold unit;
    # defaults to settings.translation_provider. Independent of
    # scoring_provider — you can e.g. evaluate with Claude but redrive
    # with a cheaper/local model, or vice versa.
    redrive_provider: Optional[str] = None
    require_human_approval: bool = False
    triggered_by: Optional[str] = None


class RedriveApprovalRequest(BaseModel):
    actor: str  # who approved/rejected — reviewer name/email/id
    reason: Optional[str] = None  # only meaningful for reject


class ProposeRequest(BaseModel):
    unit_id: str
    proposed_text: str
    proposed_by: str


class BulkApproveRequest(BaseModel):
    item_ids: List[str]
    actor: str


def _build_engine(
    scoring_provider: Optional[str], redrive_provider: Optional[str] = None,
) -> RedriveEngine:
    provider = (scoring_provider or settings.scoring_provider).lower()
    scorer = _NeverInvokedScorer() if provider == "human" else get_scorer(provider)
    # Phase 16 — redrive_provider is now an actual backend selection (not
    # just a display label): passing it to get_translation_backend()
    # builds a fresh, correctly-configured instance for that provider,
    # same "explicit provider always builds fresh" rule get_scorer() and
    # get_translation_backend() both already follow.
    redrive_backend = get_translation_backend(redrive_provider) if redrive_provider else None
    return RedriveEngine(
        scorer=scorer, scorer_label=provider, redrive_backend=redrive_backend, redrive_label=redrive_provider,
    )


@router.post("/runs", response_model=RedriveRun)
async def create_redrive_run(request: RedriveRunRequest):
    """Runs synchronously and returns the completed run — GET /runs/{id}
    still exists for polling, so a future background-task version of this
    endpoint can change how the run executes without changing the contract.

    When require_human_approval is set, below-threshold units come back with
    outcome="pending_approval" and a proposed_text instead of being applied —
    call the approve/reject endpoints below to resolve each one."""
    db = get_db()
    engine = _build_engine(request.scoring_provider, request.redrive_provider)

    run = RedriveRun(
        threshold=request.threshold, style_threshold=request.style_threshold,
        style_guide_id=request.style_guide_id, scope=request.scope,
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
    engine = await build_engine_for_item(item_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Redrive run {run_id} or item {item_id} not found")
    try:
        return await engine.approve_item(item_id, approved_by=request.actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/items/{item_id}/reject", response_model=RedriveRunItem)
async def reject_redrive_item(run_id: str, item_id: str, request: RedriveApprovalRequest):
    engine = await build_engine_for_item(item_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Redrive run {run_id} or item {item_id} not found")
    try:
        return await engine.reject_item(item_id, rejected_by=request.actor, reason=request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/bulk-approve")
async def bulk_approve_items(request: BulkApproveRequest):
    """Phase 10's editor view: approve several PENDING_APPROVAL items in
    one action (hand-picked subset, or every pending item on a page — see
    GET /api/v1/pages/pending), each resolved through its OWN run's engine
    since different items can belong to different ad-hoc proposal runs
    (every /redrive/propose call creates its own single-item run)."""
    results = []
    for item_id in request.item_ids:
        engine = await build_engine_for_item(item_id)
        if engine is None:
            results.append({"item_id": item_id, "ok": False, "error": "not found"})
            continue
        try:
            item = await engine.approve_item(item_id, approved_by=request.actor)
            results.append({"item_id": item_id, "ok": True, "item": item.model_dump()})
        except ValueError as e:
            results.append({"item_id": item_id, "ok": False, "error": str(e)})
    return {"results": results}


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
    style_threshold: Optional[float] = None,
    style_guide_id: Optional[str] = None,
    target_language: Optional[str] = None,
    source_language: Optional[str] = None,
    scoring_provider: Optional[str] = None,
):
    """Scores everything in scope and reports how many units this threshold
    would catch — same 'how many keys each cutoff would send' idea as
    peripateticware's show_report_summary, without spending redrive budget.
    style_threshold adds Phase 13's style-adherence axis to the forecast."""
    scope: Dict[str, Any] = {}
    if target_language:
        scope["target_language"] = target_language
    if source_language:
        scope["source_language"] = source_language
    engine = _build_engine(scoring_provider)
    return await engine.preview(scope, threshold, style_threshold=style_threshold, style_guide_id=style_guide_id)


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
