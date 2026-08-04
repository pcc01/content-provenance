"""
Pages API — Phase 8 non-cooperative page review. Fetches an arbitrary URL
with a headless browser, harvests/tags its translatable text, and serves a
rewritten same-origin copy the existing review overlay can highlight — no
changes required to the target site's own source.

GET /api/v1/pages/render - fetch (or re-serve a cached fetch of) a URL
"""

from fastapi.responses import HTMLResponse
from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_db
from app.core.page_fetch import PageFetchError, fetch_and_render
from app.models.schemas import TranslationMethod

router = APIRouter()


@router.get("/render", response_class=HTMLResponse)
async def render_page(
    url: str = Query(..., description="The URL to fetch and review"),
    target_language: str = Query(...),
    source_language: str = Query("en-US"),
    method: TranslationMethod = Query(TranslationMethod.AI),
    refresh: bool = Query(False, description="Force a live re-fetch instead of reusing the latest cached snapshot"),
):
    db = get_db()
    if not refresh:
        cached = await db.get_latest_page_snapshot(url, target_language)
        if cached:
            return HTMLResponse(cached.html)

    try:
        snapshot = await fetch_and_render(url, source_language, target_language, method)
    except PageFetchError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    return HTMLResponse(snapshot.html)
