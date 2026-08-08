"""Phase 14 — Cross-Document/Page Consistency Check API.

GET /api/v1/consistency/check - terminology drift + tone-spread findings
                                 over a scope of units, computed on demand
                                 (no persisted run — same "read the current
                                 state" convention as GET /redrive/preview)
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.core.consistency.checker import run_consistency_check
from app.models.schemas import ConsistencyCheckResult

router = APIRouter()


@router.get("/check", response_model=ConsistencyCheckResult)
async def check_consistency(
    target_language: Optional[str] = Query(None),
    source_language: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    unit_ids: Optional[str] = Query(None, description="Comma-separated translation unit ids"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Same `scope` convention app/api/redrive.py's endpoints already use —
    unit_ids (explicit list) takes precedence over the language/project
    filters, see app/core/db/repository.py's list_units_by_scope."""
    scope: Dict[str, Any] = {"limit": limit}
    if unit_ids:
        scope["unit_ids"] = [i.strip() for i in unit_ids.split(",") if i.strip()]
    if target_language:
        scope["target_language"] = target_language
    if source_language:
        scope["source_language"] = source_language
    if project_id:
        scope["project_id"] = project_id
    return await run_consistency_check(scope)
