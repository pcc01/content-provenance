"""
Documents API — in-context review for uploaded files: plain text / Markdown
/ CSV (flow), and Phase 7's PPTX / PDF (layout-aware, with per-shape
geometry) / DOCX (flow bilingual reader). Each paragraph / block / text
shape / table cell / speaker note becomes an ordinary TranslationUnit
(tagged with document_id + position, and for pptx/pdf/docx a linked
DocumentShape), so it gets the same translation / scoring / redrive /
provenance treatment as any other unit.

Text/Markdown/CSV render as a data-tu-id-tagged page at /documents/{id}
(DocumentViewer.tsx). A deck or PDF is reviewed on a reconstructed page
canvas (DeckReview.tsx) via /structure; a DOCX in the bilingual reader
(DocumentReview.tsx) via /segments. pptx/docx round-trip back out through
/export.{pptx,docx} using the bytes kept by app/core/documents/storage.py.

POST  /api/v1/documents/import            - upload a .txt/.md/.csv/.pptx/.pdf/.docx file
GET   /api/v1/documents                   - recent documents
GET   /api/v1/documents/{id}              - document metadata
GET   /api/v1/documents/{id}/segments     - ordered segments (flow formats)
GET   /api/v1/documents/{id}/structure    - slides/pages + shape geometry (pptx/pdf/docx)
GET   /api/v1/documents/{id}/export.pptx  - round-trip: translations written back into the deck
GET   /api/v1/documents/{id}/export.docx  - round-trip for a Word document
"""

import csv
import io
import re
from datetime import datetime
from typing import Callable, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.database import get_db
from app.core.documents import ExtractedShape, storage
from app.core.documents.docx_extract import docx_available, extract_docx
from app.core.documents.pdf_extract import extract_pdf, pdf_available
from app.core.documents.pptx_extract import extract_pptx, pptx_available
from app.core.documents.reinsert import reinsert_docx, reinsert_pptx
from app.core.prov_builder import build_provenance_record
from app.core.translation_backends import get_translation_backend
from app.models.schemas import (
    Document, DocumentFormat, DocumentShape, DocumentShapeKind,
    TranslationMethod, TranslationStatus, TranslationUnit,
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
    filename = file.filename or "document"
    lower_name = filename.lower()

    # ── Structured binary formats (Phase 7) — extracted with geometry ────
    if lower_name.endswith(".pptx"):
        return await _import_structured(
            raw, filename, DocumentFormat.PPTX, extract_pptx, pptx_available,
            "python-pptx isn't importable in this environment (it needs lxml). "
            "Install it, or import the deck's text as .txt/.md instead.",
            source_language, target_language, method, title,
        )
    if lower_name.endswith(".pdf"):
        return await _import_structured(
            raw, filename, DocumentFormat.PDF, extract_pdf, pdf_available,
            "PyMuPDF isn't installed — pip install pymupdf.",
            source_language, target_language, method, title,
        )
    if lower_name.endswith(".docx"):
        return await _import_structured(
            raw, filename, DocumentFormat.DOCX, extract_docx, docx_available,
            "python-docx isn't importable in this environment (it needs lxml).",
            source_language, target_language, method, title,
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File is not valid UTF-8 text: {e}")

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


async def _import_structured(
    raw: bytes, filename: str, fmt: DocumentFormat,
    extract_fn: Callable[[bytes], List[ExtractedShape]],
    available_fn: Callable[[], bool], unavailable_detail: str,
    source_language: str, target_language: str,
    method: TranslationMethod, title: Optional[str],
) -> Document:
    """pptx / pdf / docx — one TranslationUnit per extracted block, plus a
    DocumentShape per unit carrying page index + (where the format has it)
    a fractional bbox. Keeps the original bytes on disk for round-trip
    export."""
    if not available_fn():
        raise HTTPException(status_code=503, detail=unavailable_detail)
    try:
        shapes = extract_fn(raw)
    except Exception as e:  # corrupt/locked file, not a missing dependency
        raise HTTPException(status_code=400, detail=f"Couldn't read the {fmt.value}: {e}")
    if not shapes:
        raise HTTPException(status_code=400, detail=f"No text found in the {fmt.value}.")

    db = get_db()
    document = Document(
        title=title or filename, original_filename=filename,
        format=fmt, source_language=source_language,
        metadata={"page_count": (shapes[-1].page_index + 1) if shapes else 0},
    )
    await db.save_document(document)
    if fmt in (DocumentFormat.PPTX, DocumentFormat.PDF, DocumentFormat.DOCX):
        storage.save_original(document.id, fmt.value, raw)

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

    doc_shapes: List[DocumentShape] = []
    for position, s in enumerate(shapes):
        if backend:
            translated_text, confidence = await backend.translate(s.text, source_language, target_language)
            status = TranslationStatus.COMPLETED
        else:
            translated_text, confidence = f"[Awaiting human translation] {s.text}", 1.0
            status = TranslationStatus.PENDING

        unit = TranslationUnit(
            source_id=f"{document.id}:{position}", source_text=s.text, source_language=source_language,
            target_text=translated_text, target_language=target_language,
            translation_method=method, translated_by_agent_id=agent.id, translated_at=now,
            confidence_score=confidence, status=status,
            metadata={
                "document_id": document.id, "position": position,
                "slide_index": s.page_index, "shape_kind": s.kind,
            },
        )
        await db.save_translation_unit(unit)
        await db.save_provenance_record(await build_provenance_record(unit, []))

        doc_shapes.append(DocumentShape(
            document_id=document.id, page_index=s.page_index,
            page_width=s.page_width, page_height=s.page_height,
            shape_index=s.shape_index, reading_order=s.reading_order,
            kind=DocumentShapeKind(s.kind), x=s.x, y=s.y, w=s.w, h=s.h, unit_id=unit.id,
        ))

    await db.save_document_shapes(doc_shapes)
    return document


@router.get("")
async def list_documents(limit: int = 50):
    """Recent imported documents, newest first — the deck review's picker."""
    db = get_db()
    docs = await db.list_documents(limit=limit)
    return [d.model_dump() for d in docs]


@router.get("/{document_id}")
async def get_document(document_id: str):
    db = get_db()
    document = await db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return document.model_dump()


@router.get("/{document_id}/structure")
async def get_document_structure(document_id: str, target_language: str):
    """Phase 7 — the deck laid out for review: slides in order, each with its
    text shapes (fractional bbox + kind + reading order) joined to their
    TranslationUnit for the given target language. Speaker notes come back
    as shapes with kind='speaker_note' and no geometry."""
    db = get_db()
    document = await db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    shapes = await db.list_document_shapes(document_id)
    units = {u.id: u for u in await db.list_translation_units_for_document(document_id, target_language)}

    pages: dict = {}
    for s in shapes:
        page = pages.setdefault(s.page_index, {
            "index": s.page_index, "width": s.page_width, "height": s.page_height, "shapes": [],
        })
        unit = units.get(s.unit_id) if s.unit_id else None
        page["shapes"].append({
            "id": s.id, "kind": s.kind.value, "reading_order": s.reading_order,
            "x": s.x, "y": s.y, "w": s.w, "h": s.h,
            "unit": unit.model_dump() if unit else None,
        })

    return {
        "document": document.model_dump(),
        "pages": [pages[i] for i in sorted(pages)],
    }


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


async def _round_trip(document_id: str, target_language: str, expect_fmt: DocumentFormat):
    """Shared prep for the export.{pptx,docx} endpoints: load the doc, its
    stored original, and the target text per shape in extraction order."""
    db = get_db()
    document = await db.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if document.format != expect_fmt:
        raise HTTPException(status_code=400, detail=f"Document {document_id} is not a {expect_fmt.value}.")
    raw = storage.load_original(document_id, expect_fmt.value)
    if raw is None:
        raise HTTPException(status_code=404, detail="Original file not on disk — re-import to enable export.")

    shapes = await db.list_document_shapes(document_id)
    units = {u.id: u for u in await db.list_translation_units_for_document(document_id, target_language)}

    def target(shape) -> Optional[str]:
        u = units.get(shape.unit_id) if shape.unit_id else None
        return (u.target_text if u else None)

    return document, raw, shapes, target


@router.get("/{document_id}/export.pptx")
async def export_document_pptx(document_id: str, target_language: str):
    """Round-trip — write the target-language text back into the original
    .pptx, layout preserved. 503 if python-pptx isn't installed."""
    if not pptx_available():
        raise HTTPException(status_code=503, detail="python-pptx isn't importable in this environment.")
    _doc, raw, shapes, target = await _round_trip(document_id, target_language, DocumentFormat.PPTX)

    positioned: dict = {}
    notes: dict = {}
    for s in sorted(shapes, key=lambda s: (s.page_index, s.reading_order)):
        bucket = notes if s.kind == DocumentShapeKind.SPEAKER_NOTE else positioned
        bucket.setdefault(s.page_index, []).append(target(s) or "")

    out = reinsert_pptx(raw, positioned, notes)
    return Response(
        content=out,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{document_id}.{target_language}.pptx"'},
    )


@router.get("/{document_id}/export.docx")
async def export_document_docx(document_id: str, target_language: str):
    """Round-trip for a Word document. 503 if python-docx isn't importable."""
    if not docx_available():
        raise HTTPException(status_code=503, detail="python-docx isn't importable in this environment.")
    _doc, raw, shapes, target = await _round_trip(document_id, target_language, DocumentFormat.DOCX)

    ordered = [target(s) or "" for s in sorted(shapes, key=lambda s: s.reading_order)]
    out = reinsert_docx(raw, ordered)
    return Response(
        content=out,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{document_id}.{target_language}.docx"'},
    )
