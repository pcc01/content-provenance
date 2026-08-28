"""Phase 7 (deferred items) — PDF extraction (real, PyMuPDF has no lxml),
DOCX/PPTX round-trip + OCR graceful-degradation (lxml / the Tesseract binary
are unavailable in CI), and the original-bytes storage helper.
Run with: PYTHONPATH=. pytest tests/test_document_formats.py -v
"""

import io

import pytest

from app.core.documents import storage
from app.core.documents.docx_extract import docx_available
from app.core.documents.ocr import ocr_available
from app.core.documents.pdf_extract import extract_pdf, pdf_available


def _make_pdf() -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, 700, "Quarterly Report")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "Revenue grew across every region this quarter.")
    c.showPage()
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, 700, "Outlook")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "We expect continued momentum into next year.")
    c.showPage()
    c.save()
    return buf.getvalue()


# ── PDF extraction (real) ──────────────────────────────────────────────────

def test_pdf_available():
    assert pdf_available() is True


def test_extract_pdf_returns_blocks_with_geometry_and_a_title():
    shapes = extract_pdf(_make_pdf())
    assert {s.page_index for s in shapes} == {0, 1}
    assert any(s.kind == "title" and "Quarterly Report" in s.text for s in shapes)
    body = next(s for s in shapes if "Revenue grew" in s.text)
    assert 0.0 <= body.x <= 1.0 and 0.0 <= body.y <= 1.0 and body.w and body.h


@pytest.mark.asyncio
async def test_pdf_import_and_structure_endpoint(client):
    from app.core.database import init_db

    await init_db()
    files = {"file": ("q3.pdf", io.BytesIO(_make_pdf()), "application/pdf")}
    data = {"source_language": "en-US", "target_language": "fr-FR", "method": "ai"}
    resp = await client.post("/api/v1/documents/import", files=files, data=data)
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    assert resp.json()["format"] == "pdf"

    struct = await client.get(f"/api/v1/documents/{doc_id}/structure?target_language=fr-FR")
    assert struct.status_code == 200
    pages = struct.json()["pages"]
    assert len(pages) == 2
    first_shape = pages[0]["shapes"][0]
    assert first_shape["unit"]["target_text"].startswith("[FR]")
    assert first_shape["x"] is not None


# ── DOCX / OCR / round-trip — degradation in CI ────────────────────────────

def test_docx_unavailable_in_ci():
    assert docx_available() is False


def test_ocr_unavailable_without_tesseract_binary():
    assert ocr_available() is False


@pytest.mark.asyncio
async def test_docx_import_503(client):
    files = {"file": ("memo.docx", io.BytesIO(b"PK\x03\x04 not a docx"), "application/octet-stream")}
    data = {"source_language": "en-US", "target_language": "fr-FR", "method": "ai"}
    resp = await client.post("/api/v1/documents/import", files=files, data=data)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_export_pptx_503_when_pptx_unavailable(client):
    from app.core.database import get_db, init_db
    from app.models.schemas import Document as DocumentModel
    from app.models.schemas import DocumentFormat

    await init_db()
    db = get_db()
    doc = DocumentModel(title="d", format=DocumentFormat.PPTX, source_language="en-US")
    await db.save_document(doc)
    storage.save_original(doc.id, "pptx", b"original bytes")
    resp = await client.get(f"/api/v1/documents/{doc.id}/export.pptx?target_language=fr-FR")
    assert resp.status_code == 503  # python-pptx / lxml blocked here


@pytest.mark.asyncio
async def test_ocr_endpoint_503(client):
    from app.core.database import get_db, init_db
    from app.models.schemas import ImageAsset, ImageAssetKind

    await init_db()
    db = get_db()
    asset = ImageAsset(
        kind=ImageAssetKind.TRANSLATABLE, storage_path="nope.png",
        content_type="image/png", checksum="x",
    )
    await db.save_image_asset(asset)
    resp = await client.post(
        f"/api/v1/images/{asset.id}/ocr",
        data={"source_language": "en-US", "target_language": "fr-FR", "method": "ai"},
    )
    assert resp.status_code == 503


# ── storage helper ─────────────────────────────────────────────────────────

def test_storage_round_trips_original_bytes(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "document_storage_dir", str(tmp_path))
    assert storage.load_original("doc-1", "pptx") is None
    storage.save_original("doc-1", "pptx", b"\x01\x02\x03")
    assert storage.load_original("doc-1", "pptx") == b"\x01\x02\x03"
