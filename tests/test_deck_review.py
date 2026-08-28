"""Phase 7 — slide-deck structural extraction + the /documents/{id}/structure
endpoint. python-pptx (via lxml) isn't importable in CI, so the real .pptx
parse is covered by graceful-degradation checks; the structure endpoint and
the geometry helper are covered directly.
Run with: PYTHONPATH=. pytest tests/test_deck_review.py -v
"""

import io

import pytest

from app.core.database import get_db, init_db
from app.core.documents.pptx_extract import _frac, pptx_available
from app.models.schemas import (
    DocumentFormat, DocumentShape, DocumentShapeKind, TranslationMethod, TranslationUnit,
)
from app.models.schemas import Document as DocumentModel


def test_frac_normalizes_and_guards():
    assert _frac(457200, 9144000) == 0.05
    assert _frac(None, 100) is None
    assert _frac(50, 0) is None
    assert _frac("x", 100) is None


def test_pptx_reports_unavailable_when_not_importable():
    # lxml is blocked in this environment — extract_pptx must degrade, not raise at import.
    assert pptx_available() is False


@pytest.mark.asyncio
async def test_pptx_import_returns_503_when_unavailable(client):
    files = {"file": ("deck.pptx", io.BytesIO(b"PK\x03\x04 not really a pptx"), "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
    data = {"source_language": "en-US", "target_language": "fr-FR", "method": "ai"}
    resp = await client.post("/api/v1/documents/import", files=files, data=data)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_structure_endpoint_groups_shapes_by_slide_with_their_units(client):
    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("deck-test-agent", "SoftwareAgent")

    doc = DocumentModel(
        title="Q3 deck", original_filename="q3.pptx", format=DocumentFormat.PPTX,
        source_language="en-US", metadata={"slide_count": 2},
    )
    await db.save_document(doc)

    shapes = []
    for i, (slide, kind, x, y) in enumerate([
        (0, DocumentShapeKind.TITLE, 0.1, 0.08),
        (0, DocumentShapeKind.BODY, 0.1, 0.3),
        (1, DocumentShapeKind.TITLE, 0.1, 0.08),
        (1, DocumentShapeKind.SPEAKER_NOTE, None, None),
    ]):
        unit = TranslationUnit(
            source_id=f"{doc.id}:{i}", source_text=f"Shape {i} source", source_language="en-US",
            target_text=f"Forme {i} cible", target_language="fr-FR",
            translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
            metadata={"document_id": doc.id, "position": i, "slide_index": slide},
        )
        await db.save_translation_unit(unit)
        shapes.append(DocumentShape(
            document_id=doc.id, page_index=slide, page_width=9144000, page_height=6858000,
            shape_index=i, reading_order=i, kind=kind,
            x=x, y=y, w=0.8 if x is not None else None, h=0.15 if x is not None else None,
            unit_id=unit.id,
        ))
    await db.save_document_shapes(shapes)

    resp = await client.get(f"/api/v1/documents/{doc.id}/structure?target_language=fr-FR")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["format"] == "pptx"
    assert len(body["pages"]) == 2
    assert body["pages"][0]["index"] == 0
    assert len(body["pages"][0]["shapes"]) == 2
    assert body["pages"][0]["shapes"][0]["kind"] == "title"
    assert body["pages"][0]["shapes"][0]["unit"]["target_text"] == "Forme 0 cible"

    note_shape = body["pages"][1]["shapes"][-1]
    assert note_shape["kind"] == "speaker_note"
    assert note_shape["x"] is None


@pytest.mark.asyncio
async def test_structure_endpoint_404_for_unknown_document(client):
    resp = await client.get("/api/v1/documents/nope/structure?target_language=fr-FR")
    assert resp.status_code == 404
