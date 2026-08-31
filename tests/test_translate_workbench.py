"""
Translate Workbench — the initial-translation tab's backend:
  PATCH /translations/{id}                  inline target edit -> new version
  POST  /translations/{id}/translate        (re)translate an existing unit in place
  POST  /documents                          pasted text -> paragraph-segmented document
  POST  /documents/{id}/segments            append more paragraphs to a document
  GET   /documents/{id}/export.xliff        assemble the document as one XLIFF 2.0
  _tm_prefill                               near-exact TMX match seeds the target + mt_suggestion

Run: PYTHONPATH=. pytest tests/test_translate_workbench.py -v
(the config.py load_dotenv fix means no manual POSTGRES_* is needed)
"""

import pytest

from app.api.documents import _tm_prefill
from app.core.database import get_db
from app.models.schemas import (
    ExemplarOrigin, TranslationExemplar, TranslationMethod, TranslationStatus,
    TranslationUnit,
)

pytestmark = pytest.mark.asyncio

_THREE_PARAS = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."


# ── POST /documents (paste -> document) ────────────────────────────────────

async def test_create_text_document_splits_into_paragraph_units(client):
    resp = await client.post("/api/v1/documents", json={
        "title": "Pasted copy", "source_language": "en-US", "target_language": "fr-FR",
        "text": _THREE_PARAS, "segmentation": "document",
    })
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["format"] == "text"
    assert doc["metadata"]["segmentation"] == "document"

    seg = (await client.get(f"/api/v1/documents/{doc['id']}/segments?target_language=fr-FR")).json()
    assert [s["source_text"] for s in seg["segments"]] == [
        "First paragraph here.", "Second paragraph here.", "Third paragraph here.",
    ]
    # mock translation backend prefixes the target with [LANG]
    assert all(s["target_text"].startswith("[FR]") for s in seg["segments"])
    assert [s["metadata"]["position"] for s in seg["segments"]] == [0, 1, 2]


async def test_create_text_document_rejects_empty(client):
    resp = await client.post("/api/v1/documents", json={
        "title": "x", "source_language": "en-US", "target_language": "fr-FR", "text": "   \n\n  ",
    })
    assert resp.status_code == 400


# ── POST /documents/{id}/segments (append) ─────────────────────────────────

async def test_append_segments_extends_the_document_contiguously(client):
    doc = (await client.post("/api/v1/documents", json={
        "title": "Growing doc", "source_language": "en-US", "target_language": "de-DE",
        "text": "Alpha block.\n\nBeta block.",
    })).json()

    resp = await client.post(f"/api/v1/documents/{doc['id']}/segments", json={
        "text": "Gamma block.\n\nDelta block.",
    })
    assert resp.status_code == 200
    segs = resp.json()["segments"]
    assert [s["source_text"] for s in segs] == [
        "Alpha block.", "Beta block.", "Gamma block.", "Delta block.",
    ]
    assert [s["metadata"]["position"] for s in segs] == [0, 1, 2, 3]
    # inherited the document's existing target language, not a new one
    assert all(s["target_language"] == "de-DE" for s in segs)


async def test_append_to_missing_document_404s(client):
    resp = await client.post("/api/v1/documents/nope/segments", json={"text": "hi"})
    assert resp.status_code == 404


# ── GET /documents/{id}/export.xliff ──────────────────────────────────────

async def test_export_xliff_contains_every_segment(client):
    doc = (await client.post("/api/v1/documents", json={
        "title": "XliffMe", "source_language": "en-US", "target_language": "fr-FR",
        "text": _THREE_PARAS,
    })).json()

    resp = await client.get(f"/api/v1/documents/{doc['id']}/export.xliff?target_language=fr-FR")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xliff+xml")
    body = resp.text
    assert body.count("<segment") >= 3 or body.count("<unit") >= 3
    assert "First paragraph here." in body

    # logged as an outbound ingest event
    log = (await client.get("/api/v1/xliff/ingest-log")).json()
    assert any(e["direction"] == "out" and e["format"] == "xliff" for e in log)


async def test_export_xliff_unknown_target_404s(client):
    doc = (await client.post("/api/v1/documents", json={
        "title": "NoTarget", "source_language": "en-US", "target_language": "fr-FR", "text": "Hi there.",
    })).json()
    resp = await client.get(f"/api/v1/documents/{doc['id']}/export.xliff?target_language=ja-JP")
    assert resp.status_code == 404


# ── PATCH /translations/{id} ──────────────────────────────────────────────

async def test_patch_target_writes_a_human_edit_version(client):
    doc = (await client.post("/api/v1/documents", json={
        "title": "Editable", "source_language": "en-US", "target_language": "fr-FR", "text": "Edit me please.",
    })).json()
    unit_id = (await client.get(
        f"/api/v1/documents/{doc['id']}/segments?target_language=fr-FR"
    )).json()["segments"][0]["id"]

    resp = await client.patch(f"/api/v1/translations/{unit_id}", json={
        "target_text": "Corrigé à la main.", "edited_by": "rev@example.com",
    })
    assert resp.status_code == 200
    assert resp.json()["target_text"] == "Corrigé à la main."

    versions = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()
    assert versions[-1]["source_event"] == "human_edit"
    assert "rev@example.com" in (versions[-1]["note"] or "")


async def test_patch_identical_target_is_a_noop(client):
    doc = (await client.post("/api/v1/documents", json={
        "title": "NoopEdit", "source_language": "en-US", "target_language": "fr-FR", "text": "Leave me be.",
    })).json()
    unit = (await client.get(
        f"/api/v1/documents/{doc['id']}/segments?target_language=fr-FR"
    )).json()["segments"][0]

    before = (await client.get(f"/api/v1/translations/{unit['id']}/versions")).json()
    resp = await client.patch(f"/api/v1/translations/{unit['id']}", json={"target_text": unit["target_text"]})
    assert resp.status_code == 200
    after = (await client.get(f"/api/v1/translations/{unit['id']}/versions")).json()
    assert len(after) == len(before)


async def test_patch_missing_unit_404s(client):
    resp = await client.patch("/api/v1/translations/nope", json={"target_text": "x"})
    assert resp.status_code == 404


# ── POST /translations/{id}/translate ────────────────────────────────────

async def test_translate_unit_in_place_fills_a_pending_unit(client):
    db = get_db()
    unit = TranslationUnit(
        source_id="wb-inplace-1", source_text="Please translate this now.",
        source_language="en-US", target_text=None, target_language="fr-FR",
        translation_method=TranslationMethod.HUMAN, translated_by_agent_id="x",
        status=TranslationStatus.PENDING,
    )
    await db.save_translation_unit(unit)

    resp = await client.post(f"/api/v1/translations/{unit.id}/translate", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_text"].startswith("[FR]")
    assert body["status"] == "completed"

    versions = (await client.get(f"/api/v1/translations/{unit.id}/versions")).json()
    assert versions[-1]["source_event"] == "mt"


# ── _tm_prefill ─────────────────────────────────────────────────────────

async def test_tm_prefill_hits_on_a_near_exact_match(client):
    db = get_db()
    await db.save_translation_exemplar(TranslationExemplar(
        source_text="The quick brown fox jumps over the lazy dog.",
        target_text="Le rapide renard brun saute par-dessus le chien paresseux.",
        source_language="en-US", target_language="fr-FR", origin=ExemplarOrigin.VENDOR,
    ))

    target, ratio = await _tm_prefill(
        db, "The quick brown fox jumps over the lazy dog!", "en-US", "fr-FR",
    )
    assert target == "Le rapide renard brun saute par-dessus le chien paresseux."
    assert ratio >= 0.90


async def test_tm_prefill_misses_on_unrelated_text(client):
    db = get_db()
    await db.save_translation_exemplar(TranslationExemplar(
        source_text="Battery life is excellent.", target_text="L'autonomie est excellente.",
        source_language="en-US", target_language="fr-FR", origin=ExemplarOrigin.VENDOR,
    ))
    target, ratio = await _tm_prefill(
        db, "Completely different sentence about shipping.", "en-US", "fr-FR",
    )
    assert target is None
    assert ratio == 0.0


async def test_create_document_seeds_tm_match_metadata(client):
    db = get_db()
    tm_target = "Bienvenido a nuestra aplicación."
    await db.save_translation_exemplar(TranslationExemplar(
        source_text="Welcome to our application.", target_text=tm_target,
        source_language="en-US", target_language="es-ES", origin=ExemplarOrigin.VENDOR,
    ))
    doc = (await client.post("/api/v1/documents", json={
        "title": "TM seeded", "source_language": "en-US", "target_language": "es-ES",
        "text": "Welcome to our application!",
    })).json()

    seg = (await client.get(
        f"/api/v1/documents/{doc['id']}/segments?target_language=es-ES"
    )).json()["segments"][0]
    assert seg["target_text"] == tm_target                       # TM hit used verbatim
    assert seg["metadata"]["tm_match"] >= 0.90
    assert seg["metadata"]["mt_suggestion"].startswith("[ES]")  # MT kept as the alternative
    assert seg["translation_method"] == "hybrid"
