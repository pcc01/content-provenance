"""
Documents API — Phase 7a in-context review for plain text and Markdown
files, plus Phase 18's CSV import. Each paragraph/block (or CSV row) of an
uploaded file becomes an ordinary TranslationUnit (tagged with document_id
+ position in its metadata), so it gets the same translation/scoring/
redrive/provenance treatment as any other unit. The Review Shell's
DocumentViewer page (frontend/src/pages/DocumentViewer.tsx) fetches a
document's segments back in order and renders them as HTML tagged with
data-tu-id — the existing overlay SDK needs no changes to review them.

POST /api/v1/documents/import           - upload a .txt/.md/.csv file
GET  /api/v1/documents/{id}             - document metadata
GET  /api/v1/documents/{id}/segments    - ordered segments for a target language
"""

import csv
import io
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.core.translation_backends import get_translation_backend
from app.models.schemas import (
    Document, DocumentFormat, TranslationMethod, TranslationStatus, TranslationUnit,
)

router = APIRouter()

_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


def _split_into_blocks(text: str) -> List[str]:
    """Segments a text/Markdown file on blank lines — paragraphs, headings,
    and multi-item lists (no blank line between items) each become one
    segment. Deliberately simple: a first pass, not a full Markdown parser."""
    blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(text)]
    return [b for b in blocks if b]


def _parse_csv_blocks(text: str, source_column: Optional[str]) -> List[str]:
    """One TranslationUnit per row, taken from `source_column` — assumes a
    header row (the common shape for a CMS/spreadsheet export, e.g. a
    "key,source_text,notes" sheet). Falls back to the first column if
    `source_column` is omitted or doesn't match any header, rather than
    rejecting the whole file over a naming mismatch."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    column = source_column if source_column in reader.fieldnames else reader.fieldnames[0]
    blocks = []
    for row in reader:
        value = (row.get(column) or "").strip()
        if value:
            blocks.append(value)
    return blocks


@router.post("/import", response_model=Document, status_code=201)
async def import_document(
    file: UploadFile = File(...),
    source_language: str = Form(...),
    target_language: str = Form(...),
    method: TranslationMethod = Form(TranslationMethod.AI),
    title: Optional[str] = Form(None),
    # Phase 18 — only meaningful for CSV; which column holds the source
    # text (defaults to the first column when omitted or not found).
    source_column: Optional[str] = Form(None),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {e}")

    filename = file.filename or "document"
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        fmt = DocumentFormat.CSV
        blocks = _parse_csv_blocks(text, source_column)
    elif lower_name.endswith((".md", ".markdown")):
        fmt = DocumentFormat.MARKDOWN
        blocks = _split_into_blocks(text)
    else:
        fmt = DocumentFormat.TEXT
        blocks = _split_into_blocks(text)
    if not blocks:
        raise HTTPException(
            status_code=400,
            detail="Document is empty" if fmt != DocumentFormat.CSV
            else "No rows with text in the source column — check source_column matches a real header.",
        )

    db = get_db()
    document = Document(
        title=title or filename, original_filename=filename, format=fmt,
        source_language=source_language,
    )
    await db.save_document(document)

    if method == TranslationMethod.HUMAN:
        agent = await db.get_or_create_agent(
            name="Human Translator", agent_type="Person", metadata={"role": "human_translator"},
        )
    else:
        agent = await db.get_or_create_agent(
            name="claude-3-7-sonnet", agent_type="SoftwareAgent",
            model_version="claude-3-7-sonnet-20250219", organization="Anthropic",
        )
    backend = get_translation_backend() if method in (TranslationMethod.AI, TranslationMethod.HYBRID) else None
    now = datetime.utcnow()

    for position, block in enumerate(blocks):
        if backend:
            translated_text, confidence = await backend.translate(block, source_language, target_language)
            status = TranslationStatus.COMPLETED
        else:
            translated_text, confidence = f"[Awaiting human translation] {block}", 1.0
            status = TranslationStatus.PENDING

        unit = TranslationUnit(
            source_id=f"{document.id}:{position}", source_text=block, source_language=source_language,
            target_text=translated_text, target_language=target_language,
            translation_method=method, translated_by_agent_id=agent.id, translated_at=now,
            confidence_score=confidence, status=status,
            metadata={"document_id": document.id, "position": position},
        )
        await db.save_translation_unit(unit)
        prov_record = await build_provenance_record(unit, [])
        await db.save_provenance_record(prov_record)

    return document


@router.get("/{document_id}")
async def get_document(document_id: str):
    db = get_db()
    document = await db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return document.model_dump()


@router.get("/{document_id}/segments")
async def get_document_segments(document_id: str, target_language: str):
    db = get_db()
    document = await db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    units = await db.list_translation_units_for_document(document_id, target_language)
    return {
        "document": document.model_dump(),
        "segments": [u.model_dump() for u in units],
    }
