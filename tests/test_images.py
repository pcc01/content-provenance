"""
Tests for the image assets API (Phase 4): context screenshots and
translatable image assets with their own provenance chain.
Run with: PYTHONPATH=. pytest tests/test_images.py -v
"""

import pytest

from app.core.database import get_db

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
async def test_upload_and_fetch_context_image(client):
    files = {"file": ("screenshot.png", _PNG_BYTES, "image/png")}
    r = await client.post(
        "/api/v1/images/", files=files, data={"kind": "context", "alt_text": "Homepage hero screenshot"},
    )
    assert r.status_code == 201
    asset = r.json()
    assert asset["kind"] == "context"
    assert asset["content_type"] == "image/png"
    image_id = asset["id"]

    meta_r = await client.get(f"/api/v1/images/{image_id}")
    assert meta_r.status_code == 200
    assert meta_r.json()["alt_text"] == "Homepage hero screenshot"

    file_r = await client.get(f"/api/v1/images/{image_id}/file")
    assert file_r.status_code == 200
    assert file_r.content == _PNG_BYTES
    assert file_r.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_context_link_to_translation_unit(client):
    payload = {
        "source_text": "Context image link test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    files = {"file": ("context.png", _PNG_BYTES, "image/png")}
    image_id = (await client.post("/api/v1/images/", files=files, data={"kind": "context"})).json()["id"]

    link_r = await client.post(
        f"/api/v1/images/{image_id}/context-link",
        data={"translation_unit_id": unit_id, "note": "Shows the segment in the hero banner"},
    )
    assert link_r.status_code == 201

    linked_r = await client.get(f"/api/v1/images/context-links/{unit_id}")
    assert linked_r.status_code == 200
    linked = linked_r.json()
    assert len(linked) == 1
    assert linked[0]["id"] == image_id


@pytest.mark.asyncio
async def test_context_link_rejects_unknown_unit(client):
    files = {"file": ("context2.png", _PNG_BYTES, "image/png")}
    image_id = (await client.post("/api/v1/images/", files=files, data={"kind": "context"})).json()["id"]

    r = await client.post(
        f"/api/v1/images/{image_id}/context-link",
        data={"translation_unit_id": "does-not-exist"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_localize_image_immediately_with_target(client):
    files = {"file": ("banner-en.png", _PNG_BYTES, "image/png")}
    source_id = (await client.post("/api/v1/images/", files=files, data={"kind": "translatable"})).json()["id"]

    target_files = {"target_file": ("banner-de.png", _PNG_BYTES, "image/png")}
    r = await client.post(
        f"/api/v1/images/{source_id}/localize",
        files=target_files,
        data={"source_language": "en-US", "target_language": "de-DE", "method": "human", "translator_name": "Jane"},
    )
    assert r.status_code == 201
    itu = r.json()
    assert itu["status"] == "completed"
    assert itu["target_image_id"] is not None
    assert itu["source_image_id"] == source_id

    # /api/v1/provenance/{id} is TranslationUnit-specific (it 404s on
    # anything get_translation_unit() doesn't recognize) — Phase 4 doesn't
    # add an image-specific provenance route, so verify directly via the repo.
    db = get_db()
    prov = await db.get_provenance_by_unit(itu["id"])
    assert prov is not None
    entity_types = [e.entity_type for e in prov.entities]
    assert "SourceImage" in entity_types
    assert "TranslatedImage" in entity_types
    assert any(rel["type"] == "wasDerivedFrom" for rel in prov.relations)


@pytest.mark.asyncio
async def test_localize_image_pending_then_attach_target(client):
    files = {"file": ("poster-en.png", _PNG_BYTES, "image/png")}
    source_id = (await client.post("/api/v1/images/", files=files, data={"kind": "translatable"})).json()["id"]

    r = await client.post(
        f"/api/v1/images/{source_id}/localize",
        data={"source_language": "en-US", "target_language": "ja-JP", "method": "human"},
    )
    assert r.status_code == 201
    itu = r.json()
    assert itu["status"] == "pending"
    assert itu["target_image_id"] is None

    target_files = {"target_file": ("poster-ja.png", _PNG_BYTES, "image/png")}
    attach_r = await client.put(f"/api/v1/images/localize/{itu['id']}/target", files=target_files)
    assert attach_r.status_code == 200
    updated = attach_r.json()
    assert updated["status"] == "completed"
    assert updated["target_image_id"] is not None

    got_r = await client.get(f"/api/v1/images/localize/{itu['id']}")
    assert got_r.status_code == 200
    assert got_r.json()["status"] == "completed"
