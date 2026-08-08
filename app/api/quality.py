"""Phase 15 — Automatic Quality Metrics API (non-LLM: METEOR, COMET-Kiwi).
Phase 16 adds the standalone LLM-judge "evaluate" endpoint.

POST /api/v1/quality/meteor-compare        - ad-hoc METEOR between any two strings
GET  /api/v1/quality/{unit_id}/automatic   - a unit's automatic-metric score history
POST /api/v1/quality/comet-score           - batch COMET-Kiwi QE scoring (offline/admin)
POST /api/v1/quality/evaluate              - score one unit with a chosen LLM-judge provider on demand
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.scoring.automatic.comet_kiwi import comet_kiwi_available, score_comet_kiwi_batch
from app.core.scoring.automatic.meteor import compute_meteor
from app.core.scoring.base import ScoreResult
from app.core.scoring.factory import get_scorer
from app.models.schemas import AutomaticMetricScore, QualityScore

router = APIRouter()


class MeteorCompareRequest(BaseModel):
    hypothesis: str = Field(..., min_length=1)
    reference: str = Field(..., min_length=1)


class MeteorCompareResponse(BaseModel):
    score: Optional[float]  # 0-100, None if nltk/wordnet unavailable


class CometScoreRequest(BaseModel):
    unit_ids: List[str] = Field(..., min_length=1, max_length=200)


class EvaluateRequest(BaseModel):
    unit_id: str
    # Phase 16 — any LLM-judge scoring provider: "claude" | "ollama" |
    # "openai" | "gemini" | "lmstudio" | "vllm". None = settings.scoring_provider.
    # Runs through the same CompositeScorer as redrive (get_scorer()), so
    # deterministic.py's free checks still short-circuit obvious cases
    # before spending a model call.
    provider: Optional[str] = None


@router.post("/meteor-compare", response_model=MeteorCompareResponse)
async def meteor_compare(request: MeteorCompareRequest):
    """Ad-hoc METEOR between any two strings — the same computation
    RedriveEngine runs automatically as a post-redrive regression check
    (app/core/redrive/engine.py's _record_meteor_regression), exposed
    directly for manual comparison (e.g. a curated golden-set reference)."""
    score = await compute_meteor(request.hypothesis, request.reference)
    return MeteorCompareResponse(score=score)


@router.get("/{unit_id}/automatic", response_model=List[AutomaticMetricScore])
async def get_automatic_scores(unit_id: str):
    db = get_db()
    if not await db.get_translation_unit(unit_id):
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    return await db.list_automatic_metric_scores(unit_id)


@router.post("/comet-score")
async def comet_score_batch(request: CometScoreRequest):
    """Batch, offline/admin-triggered COMET-Kiwi (reference-free QE)
    scoring — deliberately NOT on any live translation-request or redrive
    path (see docs/quality-evaluation-research.md §3.2: CPU inference on a
    transformer-scale model doesn't fit a live-latency budget, and the
    checkpoint's CC-BY-NC-SA license is a decision this project has scoped
    to internal/non-commercial evaluation use, not something to invoke by
    default on every translation)."""
    if not comet_kiwi_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "unbabel-comet not installed, or the wmt22-cometkiwi-da checkpoint hasn't been "
                "downloaded/license-accepted on Hugging Face. See app/core/scoring/automatic/"
                "comet_kiwi.py and docs/quality-evaluation-research.md §3."
            ),
        )
    db = get_db()
    units = []
    for unit_id in request.unit_ids:
        unit = await db.get_translation_unit(unit_id)
        if unit:
            units.append(unit)
    results = await score_comet_kiwi_batch(units)
    for unit, score in zip(units, results):
        if score is not None:
            await db.save_automatic_metric_score(AutomaticMetricScore(
                unit_id=unit.id, metric="comet_kiwi", score=round(score * 100, 2), raw_score=score,
                reference_type=None, detail={"checkpoint": "Unbabel/wmt22-cometkiwi-da"},
            ))
    return {
        "scored_count": sum(1 for s in results if s is not None),
        "requested_count": len(request.unit_ids),
        "found_count": len(units),
    }


@router.post("/evaluate", response_model=QualityScore)
async def evaluate_unit(request: EvaluateRequest):
    """Standalone evaluation — score an existing unit with a specific
    LLM-judge provider on demand, independent of the redrive threshold
    loop. This is the "evaluate" capability requested alongside
    translate/retranslate: a reviewer picking Claude vs. GPT-4o vs. a
    local Tower+ checkpoint to see how they each read one unit, without
    having to run (or requeue) a full redrive pass.

    Mirrors RedriveEngine._score_unit's resilience contract exactly (see
    app/core/redrive/engine.py): a scorer failure — missing credentials,
    a network error, an unparseable model response — degrades to
    needs_review=True rather than raising past this point."""
    db = get_db()
    unit = await db.get_translation_unit(request.unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {request.unit_id} not found")

    scorer_name = (request.provider or settings.scoring_provider).lower()
    try:
        scorer = get_scorer(request.provider)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await scorer.score(unit)
    except Exception as e:
        result = ScoreResult(score=None, reasons=["scorer_error"], raw_response=str(e), needs_review=True)

    record = QualityScore(
        unit_id=unit.id,
        score=result.score,
        scorer="deterministic" if result.deterministic else scorer_name,
        reasons=result.reasons,
        errors=result.errors,
        raw_response=result.raw_response,
        needs_review=result.needs_review,
        hard_fail=result.hard_fail,
    )
    return await db.save_quality_score(record)
