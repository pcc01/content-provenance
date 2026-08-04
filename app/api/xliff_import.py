"""XLIFF 2.0 Import API — the "entering the system" counterpart to
xliff_export.py, and the shared ledger view for both directions."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.database import get_db
from app.models.schemas import IngestDirection
from app.xliff.xliff_import import import_xliff

router = APIRouter()


@router.post("/import")
async def import_xliff_document(
    file: UploadFile = File(...),
    source_system: str = Form("unknown"),
):
    """Ingest an external XLIFF 2.0 document — creates/updates TranslationUnits
    and their version history, synthesizing minimal provenance for units that
    arrive with none. Logged in ingest_events (direction=in) alongside every
    export (direction=out) so the full entering/leaving ledger is queryable."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {e}")

    try:
        units = await import_xliff(content, source_system=source_system)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = get_db()
    await db.log_ingest_event(
        direction=IngestDirection.IN, format="xliff", source_system=source_system,
        unit_count=len(units),
    )
    return {
        "imported_count": len(units),
        "translation_unit_ids": [u.id for u in units],
    }


@router.get("/ingest-log")
async def get_ingest_log(limit: int = 100):
    """Everything that has entered or left the system as an XLIFF document —
    the queryable side of the 'everything entering and leaving the system'
    ledger (app.models.schemas.IngestEvent)."""
    db = get_db()
    events = await db.list_ingest_events(limit=limit)
    return [e.model_dump() for e in events]
