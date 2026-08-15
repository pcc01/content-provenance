"""CMS Integration API — ROADMAP.md's "CMS push/pull content API".

POST /api/v1/integrations/cms/push    - write a translation + its full
                                         provenance into a CMS entry
GET  /api/v1/integrations/cms/pull    - read a field's current value from
                                         a CMS entry (to seed a translation)
GET  /api/v1/integrations/cms/status  - is the given provider configured?

Strapi is the only working provider today; the request/response shape is
provider-agnostic (see app/core/integrations/factory.py for how
Directus/Payload are prepared for).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.cms_service import pull_source_from_cms, push_translation_to_cms
from app.core.config import settings
from app.models.schemas import CMSPullResponse, CMSPushRequest, CMSPushResponse

router = APIRouter()


@router.post("/push", response_model=CMSPushResponse)
async def push_to_cms(request: CMSPushRequest):
    try:
        result = await push_translation_to_cms(
            unit_id=request.unit_id,
            provider=request.provider,
            content_type=request.content_type,
            entry_id=request.entry_id,
            field_name=request.field_name,
            locale=request.locale,
            provenance_field=request.provenance_field,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/pull", response_model=CMSPullResponse)
async def pull_from_cms(
    provider: str = Query("strapi"),
    content_type: str = Query(...),
    entry_id: str = Query(...),
    field_name: str = Query(...),
    locale: Optional[str] = Query(None),
):
    try:
        result = await pull_source_from_cms(
            provider=provider, content_type=content_type, entry_id=entry_id,
            field_name=field_name, locale=locale,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/status")
async def cms_status(provider: str = Query("strapi")):
    """Reports whether `provider` is configured — never echoes back the
    token itself."""
    provider = provider.lower()
    if provider == "strapi":
        configured = bool(settings.strapi_base_url and settings.strapi_api_token)
        return {"provider": provider, "configured": configured, "base_url": settings.strapi_base_url or None}
    if provider in ("directus", "payload"):
        return {"provider": provider, "configured": False, "detail": f"{provider} integration is not implemented yet"}
    raise HTTPException(status_code=400, detail=f"Unknown CMS provider: {provider!r}")
