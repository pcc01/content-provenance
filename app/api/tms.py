"""TMS Integration API (Crowdin) — the workflow-level peer of the CMS
integration in app/api/integrations.py.

POST /api/v1/integrations/tms/send           push a unit's source string
                                             (+ MT draft as a suggestion,
                                             + quality score/flags as a comment)
POST /api/v1/integrations/tms/setup-webhook  register the approval webhook
GET  /api/v1/integrations/tms/status         is the provider configured?

Phase 2 adds POST /webhook and GET /pull to bring approved translations back.
"""

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.tms_service import send_unit_for_review
from app.core.integrations.factory import get_tms_integration
from app.models.schemas import TMSSendRequest, TMSSendResponse, TMSStatusResponse

router = APIRouter()

# The events we ask Crowdin to notify us about.
_WEBHOOK_EVENTS = ["suggestion.approved"]


@router.post("/send", response_model=TMSSendResponse)
async def tms_send(request: TMSSendRequest):
    try:
        result = await send_unit_for_review(
            request.unit_id,
            provider=request.provider,
            include_mt_draft=request.include_mt_draft,
            include_quality_note=request.include_quality_note,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/setup-webhook")
async def tms_setup_webhook(payload: dict):
    """One-time: point the TMS project's approval webhook at this app.
    `callback_url` must already carry `?secret=<CROWDIN_WEBHOOK_SECRET>` —
    the /webhook endpoint (Phase 2) checks it on every inbound POST."""
    callback_url = (payload or {}).get("callback_url")
    if not callback_url:
        raise HTTPException(status_code=400, detail="callback_url is required")
    try:
        integration = get_tms_integration()
        result = await integration.ensure_webhook(callback_url=callback_url, events=_WEBHOOK_EVENTS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"events": _WEBHOOK_EVENTS, **result}


@router.get("/status", response_model=TMSStatusResponse)
async def tms_status():
    """Whether the configured TMS provider is usable — never echoes the token."""
    provider = (settings.tms_provider or "crowdin").lower()
    if provider == "crowdin":
        configured = bool(settings.crowdin_project_id and settings.crowdin_api_token)
        return TMSStatusResponse(
            provider=provider,
            configured=configured,
            project_id=settings.crowdin_project_id or None,
            detail=None if configured else "set CROWDIN_PROJECT_ID and CROWDIN_API_TOKEN",
        )
    return TMSStatusResponse(
        provider=provider, configured=False,
        detail=f"{provider} TMS integration is not implemented yet",
    )
