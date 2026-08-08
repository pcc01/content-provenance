"""Translation Memory (TMX) import API — the legacy-vendor-TM counterpart
to app/api/xliff_import.py. See app/tm/tmx_import.py's docstring for why
this creates TranslationExemplars, not TranslationUnits."""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.database import get_db
from app.models.schemas import IngestDirection
from app.tm.tmx_import import import_tmx

router = APIRouter()


@router.post("/import")
async def import_tmx_document(
    file: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...),
    source_system: str = Form("unknown"),
    style_guide_id: Optional[str] = Form(None),
):
    """Ingest a TMX 1.4 translation-memory export — creates
    TranslationExemplar rows (retrieval context for
    app/core/graph/retrieval.py) tagged with the vendor's identity via
    ProvenanceAgent.organization. Logged in the same ingest_events ledger
    as XLIFF import/export (format="tmx")."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {e}")

    try:
        exemplars = await import_tmx(
            content, source_language=source_language, target_language=target_language,
            source_system=source_system, style_guide_id=style_guide_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = get_db()
    await db.log_ingest_event(
        direction=IngestDirection.IN, format="tmx", source_system=source_system,
        unit_count=len(exemplars),
    )
    return {
        "imported_count": len(exemplars),
        "exemplar_ids": [e.id for e in exemplars],
    }
