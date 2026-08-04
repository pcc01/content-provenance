"""
Tests for the documents API (Phase 7a): plain text/Markdown files reviewed
via the same in-context overlay as a live page — each segment is an
ordinary TranslationUnit tagged with document_id + position.
Run with: PYTHONPATH=. pytest tests/test_documents.py -v
"""

import pytest

_MARKDOWN = (
    b"# Welcome\n\n"
    b"This is the **first** paragraph.\n\n"
    b"This is the second paragraph."
)

_TEXT = b"First line of the document.\n\nSecond paragraph here."


@pytest.mark.asyncio
async def test_import_markdown_document_and_fetch_segments(client):
    files = {"file": ("readme.md", _MARKDOWN, "text/markdown")}
    r = await client.post(
        "/api/v1/documents/import",
        files=files,
        data={"source_language": "en-US", "target_language": "fr-FR", "method": "ai"},
    )
    assert r.status_code == 201
    document = r.json()
    assert document["format"] == "markdown"
    assert document["original_filename"] == "readme.md"
    assert document["title"] == "readme.md"
    document_id = document["id"]

    meta_r = await client.get(f"/api/v1/documents/{document_id}")
    assert meta_r.status_code == 200
    assert meta_r.json()["id"] == document_id

    seg_r = await client.get(f"/api/v1/documents/{document_id}/segments", params={"target_language": "fr-FR"})
    assert seg_r.status_code == 200
    body = seg_r.json()
    assert body["document"]["id"] == document_id
    segments = body["segments"]
    assert len(segments) == 3
    # Reading order preserved, and each source block survived unmangled.
    assert segments[0]["source_text"] == "# Welcome"
    assert segments[1]["source_text"] == "This is the **first** paragraph."
    assert segments[2]["source_text"] == "This is the second paragraph."
    assert all(s["target_text"].startswith("[FR] ") for s in segments)
    assert all(s["metadata"]["document_id"] == document_id for s in segments)
    assert [s["metadata"]["position"] for s in segments] == [0, 1, 2]


@pytest.mark.asyncio
async def test_import_plain_text_document(client):
    files = {"file": ("notes.txt", _TEXT, "text/plain")}
    r = await client.post(
        "/api/v1/documents/import",
        files=files,
        data={"source_language": "en-US", "target_language": "de-DE", "method": "ai", "title": "My Notes"},
    )
    assert r.status_code == 201
    document = r.json()
    assert document["format"] == "text"
    assert document["title"] == "My Notes"

    seg_r = await client.get(
        f"/api/v1/documents/{document['id']}/segments", params={"target_language": "de-DE"}
    )
    segments = seg_r.json()["segments"]
    assert len(segments) == 2
    assert segments[0]["source_text"] == "First line of the document."


@pytest.mark.asyncio
async def test_import_human_method_leaves_segments_pending(client):
    files = {"file": ("draft.txt", b"Needs a human translator.", "text/plain")}
    r = await client.post(
        "/api/v1/documents/import",
        files=files,
        data={"source_language": "en-US", "target_language": "ja-JP", "method": "human"},
    )
    document = r.json()

    seg_r = await client.get(
        f"/api/v1/documents/{document['id']}/segments", params={"target_language": "ja-JP"}
    )
    segments = seg_r.json()["segments"]
    assert len(segments) == 1
    assert segments[0]["status"] == "pending"
    assert segments[0]["target_text"].startswith("[Awaiting human translation]")


@pytest.mark.asyncio
async def test_import_rejects_empty_document(client):
    files = {"file": ("empty.txt", b"   \n\n  ", "text/plain")}
    r = await client.post(
        "/api/v1/documents/import",
        files=files,
        data={"source_language": "en-US", "target_language": "fr-FR"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_unknown_document_404s(client):
    r = await client.get("/api/v1/documents/does-not-exist")
    assert r.status_code == 404
