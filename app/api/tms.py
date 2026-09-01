"""TMS Integration API (Crowdin) — the workflow-level peer of the CMS
integration in app/api/integrations.py.

POST /api/v1/integrations/tms/send           push a unit's source string
                                             (+ MT draft as a suggestion,
                                             + quality score/flags as a comment)
POST /api/v1/integrations/tms/setup-webhook  register the approval webhook
POST /api/v1/integrations/tms/webhook        receive an approved translation
                                             (verified by ?secret=)
GET  /api/v1/integrations/tms/pull           polling fallback: fetch + apply a
                                             unit's approved translation
GET  /api/v1/integrations/tms/status         is the provider configured?
"""

import hmac

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.core.tms_service import apply_approved_translation, apply_from_poll, send_unit_for_review
from app.core.integrations.factory import get_tms_integration
from app.models.schemas import (
    TMSSendRequest, TMSSendResponse, TMSStatusResponse, TMSWebhookResult,
)

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


@router.post("/webhook", response_model=TMSWebhookResult)
async def tms_webhook(request: Request, secret: str = Query("")):
    """Inbound approval webhook. Auth is the shared `?secret=` appended to
    the callback URL at setup time; the body is parsed by the provider
    connector into a normalized approval event and applied."""
    expected = settings.crowdin_webhook_secret
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=401, detail="bad or missing webhook secret")

    body = await request.body()
    try:
        integration = get_tms_integration()
        event = integration.parse_webhook_event(dict(request.headers), body, expected)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event is None:
        return TMSWebhookResult(applied=False, detail="event ignored")
    return TMSWebhookResult(**await apply_approved_translation(event))


@router.get("/pull", response_model=TMSWebhookResult)
async def tms_pull(unit_id: str = Query(...)):
    """Polling fallback: fetch this unit's current approved translation from
    the TMS and apply it if there is one and it differs."""
    try:
        return TMSWebhookResult(**await apply_from_poll(unit_id))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
