"""
Pages API — Phase 8 non-cooperative page review, Phase 9 page history,
Phase 10 page-level notes. Fetches an arbitrary URL with a headless
browser, harvests/tags its translatable text, and serves a rewritten
same-origin copy the existing review overlay can highlight — no changes
required to the target site's own source. Phase 9 adds time-travel:
browse, diff, and (via the translations API's revert endpoint) restore a
page's past versions. Phase 10 adds a way for a browser extension's content
script to reuse the SAME harvest/match engine against a real live tab
instead of an anonymous Playwright fetch (see app/core/page_fetch.py's
match_or_create_units — no headless browser involved here, the real tab
already IS the browser), plus notes that attach to a whole page
(url+target_language) instead of one segment — for observations from a
live review session that don't map to a single unit.

POST /api/v1/pages/harvest         - Phase 10: match/create units for an already-harvested item list
GET  /api/v1/pages/render          - fetch (or re-serve/reconstruct) a URL
GET  /api/v1/pages/history         - timeline of points where something on the page changed
GET  /api/v1/pages/diff            - which segments differ between two points in time
GET  /api/v1/pages/notes           - page-level notes thread
POST /api/v1/pages/notes           - add a page-level note
PUT  /api/v1/pages/notes/{id}/resolve - mark a page-level note resolved/unresolved
"""

from datetime import datetime
from typing import List, Optional

from fastapi.responses import HTMLResponse
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.database import get_db
from app.core.page_fetch import PageFetchError, fetch_and_render, match_or_create_units
from app.core.page_history import diff_page, get_page_timeline, reconstruct_page_as_of
from app.models.schemas import ReviewNote, TranslationMethod

router = APIRouter()


class PageNoteCreateRequest(BaseModel):
    url: str
    target_language: str
    author: str
    body: str
    parent_id: Optional[str] = None


class HarvestItem(BaseModel):
    idx: int
    domPath: str
    text: str


class HarvestRequest(BaseModel):
    url: str
    target_language: str
    source_language: str = "en-US"
    method: TranslationMethod = TranslationMethod.AI
    items: List[HarvestItem]


@router.post("/harvest")
async def harvest_page(request: HarvestRequest):
    """Phase 10: the caller (an extension content script running in a real
    live tab) already walked the DOM itself and has the {idx, domPath,
    text} list — this only does the matching/translation step, identical
    to what fetch_and_render does internally for Phase 8's Playwright path.
    No text-swap response needed: the extension tags elements directly with
    the returned tuId and leaves the live page's text alone (see Phase 10
    in the plan for why)."""
    items = [item.model_dump() for item in request.items]
    mapping, _ = await match_or_create_units(
        request.url, request.source_language, request.target_language, request.method, items,
    )
    return {"mapping": mapping}


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


@router.get("/pending")
async def list_pending_changes(url: str = Query(...), target_language: str = Query(...)):
    """Phase 10's editor view: every proposed-but-not-yet-approved change
    on this page, source vs. current vs. proposed text, ready for the
    reviewer to approve individually or all at once (see
    POST /api/v1/redrive/items/bulk-approve)."""
    db = get_db()
    snapshot = await db.get_latest_page_snapshot(url, target_language)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {url} ({target_language})")

    items = await db.list_pending_redrive_items_for_units(snapshot.harvested_unit_ids)
    pending = []
    for item in items:
        unit = await db.get_translation_unit(item.unit_id)
        pending.append({
            "item_id": item.id,
            "run_id": item.run_id,
            "unit_id": item.unit_id,
            "source_text": unit.source_text if unit else None,
            "current_text": unit.target_text if unit else None,
            "proposed_text": item.proposed_text,
        })
    return {"url": url, "target_language": target_language, "pending": pending}


@router.get("/notes")
async def list_page_notes(url: str = Query(...), target_language: str = Query(...)):
    db = get_db()
    notes = await db.list_page_notes(url, target_language)
    return [n.model_dump() for n in notes]


@router.post("/notes", response_model=ReviewNote, status_code=201)
async def create_page_note(request: PageNoteCreateRequest):
    db = get_db()
    note = ReviewNote(
        page_url=request.url, target_language=request.target_language,
        author=request.author, body=request.body, parent_id=request.parent_id,
    )
    await db.save_review_note(note)
    return note


@router.put("/notes/{note_id}/resolve", response_model=ReviewNote)
async def resolve_page_note(note_id: str, resolved: bool = True):
    db = get_db()
    note = await db.resolve_review_note(note_id, resolved=resolved)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return note
