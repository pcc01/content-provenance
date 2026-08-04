"""
Pages API — Phase 8 non-cooperative page review, Phase 9 page history.
Fetches an arbitrary URL with a headless browser, harvests/tags its
translatable text, and serves a rewritten same-origin copy the existing
review overlay can highlight — no changes required to the target site's
own source. Phase 9 adds time-travel: browse, diff, and (via the
translations API's revert endpoint) restore a page's past versions.

GET /api/v1/pages/render  - fetch (or re-serve/reconstruct) a URL
GET /api/v1/pages/history - timeline of points where something on the page changed
GET /api/v1/pages/diff    - which segments differ between two points in time
"""

from datetime import datetime

from fastapi.responses import HTMLResponse
from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_db
from app.core.page_fetch import PageFetchError, fetch_and_render
from app.core.page_history import diff_page, get_page_timeline, reconstruct_page_as_of
from app.models.schemas import TranslationMethod

router = APIRouter()


@router.get("/render", response_class=HTMLResponse)
async def render_page(
    url: str = Query(..., description="The URL to fetch and review"),
    target_language: str = Query(...),
    source_language: str = Query("en-US"),
    method: TranslationMethod = Query(TranslationMethod.AI),
    refresh: bool = Query(False, description="Force a live re-fetch instead of reusing the latest cached snapshot"),
    as_of: datetime = Query(None, description="Phase 9: reconstruct the page as it looked at this point in time"),
):
    db = get_db()

    if as_of is not None:
        html = await reconstruct_page_as_of(url, target_language, as_of)
        if html is None:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshot of {url} ({target_language}) exists at or before {as_of.isoformat()}",
            )
        return HTMLResponse(html)

    if not refresh:
        cached = await db.get_latest_page_snapshot(url, target_language)
        if cached:
            return HTMLResponse(cached.html)

    try:
        snapshot = await fetch_and_render(url, source_language, target_language, method)
    except PageFetchError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    return HTMLResponse(snapshot.html)


@router.get("/history")
async def page_history(url: str = Query(...), target_language: str = Query(...)):
    timestamps = await get_page_timeline(url, target_language)
    if timestamps is None:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {url} ({target_language})")
    return {"url": url, "target_language": target_language, "timestamps": [t.isoformat() for t in timestamps]}


@router.get("/diff")
async def page_diff(
    url: str = Query(...),
    target_language: str = Query(...),
    from_ts: datetime = Query(..., description="Earlier point in time to compare from"),
    to_ts: datetime = Query(..., description="Later point in time to compare to"),
):
    changes = await diff_page(url, target_language, from_ts, to_ts)
    if changes is None:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {url} ({target_language})")
    return {"url": url, "target_language": target_language, "changes": changes}
