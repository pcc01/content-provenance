"""JSON Provenance Document Import API — the JSON peer of app/api/xliff_import.py.

Mounted BEFORE json_export under the same /api/v1/json prefix — same
reason as xliff_import vs xliff_export: /import and /ingest-log need to
match before json_export's catch-all /{unit_id} route treats "import" as
a unit_id.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.database import get_db
from app.models.schemas import IngestDirection
from app.provenance_json.json_import import import_provenance_json

router = APIRouter()


@router.post("/import")
async def import_json_document(
    file: UploadFile = File(...),
    source_system: str = Form("unknown"),
):
    """Ingest an external JSON document — this system's own extensive
    export, or a bare/minimal JSON file (see
    app/provenance_json/json_service.py's parse_json_document for exactly
    how lenient acceptance is) — creating/updating TranslationUnits and
    synthesizing full provenance for whatever arrives without any."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {e}")

    try:
        units = await import_provenance_json(content, source_system=source_system)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = get_db()
    await db.log_ingest_event(
        direction=IngestDirection.IN, format="json", source_system=source_system,
        unit_count=len(units),
    )
    return {
        "imported_count": len(units),
        "translation_unit_ids": [u.id for u in units],
    }


@router.get("/ingest-log")
async def get_ingest_log(limit: int = 100):
    """Passthrough to the same entering/leaving ledger app/api/xliff_import.py
    exposes at /api/v1/xliff/ingest-log — IngestEvent.format already
    distinguishes "xliff" from "json" entries, and list_ingest_events
    already returns every format unfiltered, so this is the same ledger
    under a second, format-appropriate path, not a second ledger."""
    db = get_db()
    events = await db.list_ingest_events(limit=limit)
    return [e.model_dump() for e in events]
