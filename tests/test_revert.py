"""
Tests for Phase 9's revert endpoint: restoring a TranslationUnit's
target_text to what an earlier version had, without rewriting history.
Run with: PYTHONPATH=. pytest tests/test_revert.py -v
"""

import pytest

from app.core.database import get_db


@pytest.mark.asyncio
async def test_revert_creates_new_version_and_restores_text(client):
    payload = {
        "source_text": "Revert test source.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    original_version = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()[0]
    original_text = original_version["target_text"]

    # Simulate a human edit creating a second version — there's no public
    # "plain edit" endpoint yet, so go through the repository directly, the
    # same way the redrive engine or an XLIFF import would.
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    unit.target_text = "Edited text, not the original."
    await db.save_translation_unit(unit, version_source_event="human_edit", version_note="test edit")

    versions_after_edit = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()
    assert len(versions_after_edit) == 2
    assert versions_after_edit[1]["target_text"] == "Edited text, not the original."

    revert_r = await client.post(
        f"/api/v1/translations/{unit_id}/versions/{original_version['id']}/revert",
        params={"reverted_by": "tester"},
    )
    assert revert_r.status_code == 200
    reverted_unit = revert_r.json()
    assert reverted_unit["target_text"] == original_text

    versions_after_revert = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()
    assert len(versions_after_revert) == 3
    assert versions_after_revert[2]["source_event"] == "revert"
    assert versions_after_revert[2]["target_text"] == original_text
    assert "tester" in versions_after_revert[2]["note"]

    prov_r = await client.get(f"/api/v1/provenance/{unit_id}")
    relations = prov_r.json()["provenance"]["relations"]
    revision_relations = [r for r in relations if r["type"] == "wasRevisionOf"]
    assert len(revision_relations) == 2


@pytest.mark.asyncio
async def test_revert_is_a_noop_when_target_already_matches(client):
    payload = {
        "source_text": "No-op revert test.",
        "source_language": "en-US",
        "target_language": "es-ES",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]
    only_version = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()[0]

    r = await client.post(f"/api/v1/translations/{unit_id}/versions/{only_version['id']}/revert")
    assert r.status_code == 200

    versions = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()
    assert len(versions) == 1  # reverting to the already-current version writes nothing new


@pytest.mark.asyncio
async def test_revert_rejects_unknown_version(client):
    payload = {
        "source_text": "Unknown version test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.post(f"/api/v1/translations/{unit_id}/versions/does-not-exist/revert")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revert_rejects_unknown_unit(client):
    r = await client.post("/api/v1/translations/does-not-exist/versions/also-missing/revert")
    assert r.status_code == 404
