"""
JSON Provenance Document API Tests — the JSON peer of the XLIFF tests in
tests/test_api.py (test_xliff_preview / test_xliff_download /
test_xliff_import_new_unit / test_xliff_export_then_reimport_creates_version_and_revision /
test_ingest_log_tracks_both_directions), plus JSON-specific coverage for
lenient/minimal-input import.

Run with: PYTHONPATH=. pytest tests/test_json_export.py -v
"""

import json

import pytest


@pytest.mark.asyncio
async def test_json_preview(client):
    payload = {
        "source_text": "JSON export test content.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/json/{unit_id}/preview")
    assert r.status_code == 200
    doc = r.json()
    assert doc["units"][0]["source_text"] == "JSON export test content."
    assert doc["units"][0]["id"] == unit_id


@pytest.mark.asyncio
async def test_json_download(client):
    payload = {
        "source_text": "JSON download test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "mobile_app",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/json/{unit_id}")
    assert r.status_code == 200
    assert "json" in r.headers.get("content-type", "").lower()
    assert "attachment" in r.headers.get("content-disposition", "")

    doc = r.json()
    assert doc["document_id"] == unit_id
    assert doc["prov_conformance"] == "W3C PROV-DM 2013"
    unit = doc["units"][0]
    assert unit["source_text"] == "JSON download test."
    assert unit["target_language"] == "de-DE"
    # Full embedded provenance, deployments, and version history — not just
    # the bare unit fields.
    assert unit["provenance"]["bundle_id"]
    assert unit["provenance"]["entities"]
    assert unit["provenance"]["relations"]
    assert isinstance(unit["deployments"], list)
    assert isinstance(unit["version_history"], list)


# ── JSON Import — plain/minimal input + version history + ingest ledger ───────

@pytest.mark.asyncio
async def test_json_import_new_unit(client):
    """Importing a document with no embedded provenance should still
    succeed — provenance is synthesized (external:{source_system} agent,
    method defaulted to human) rather than the import failing."""
    doc = {
        "units": [
            {
                "id": "json-ext-unit-1",
                "source_text": "Imported from an external tool.",
                "source_language": "en-US",
                "target_text": "Importé depuis un outil externe.",
                "target_language": "fr-FR",
                "status": "translated",
            }
        ]
    }
    files = {"file": ("external.json", json.dumps(doc), "application/json")}
    r = await client.post("/api/v1/json/import", files=files, data={"source_system": "AcmeCMS"})
    assert r.status_code == 200
    data = r.json()
    assert data["imported_count"] == 1
    unit_id = data["translation_unit_ids"][0]
    assert unit_id == "json-ext-unit-1"

    got = await client.get(f"/api/v1/translations/{unit_id}")
    assert got.status_code == 200
    unit = got.json()
    assert unit["source_text"] == "Imported from an external tool."
    assert unit["target_text"] == "Importé depuis un outil externe."
    assert unit["metadata"]["import_source"] == "AcmeCMS"
    assert unit["metadata"]["method_inferred"] is False


@pytest.mark.asyncio
async def test_json_import_minimal_shape_enriches_with_provenance(client):
    """The core ask: hand it a plain/minimal JSON file (bare array, no
    wrapper, no id, no provenance, alias field names) and get back a fully
    provenance-enriched document on export."""
    minimal = [
        {"sourceText": "Bare minimal input.", "targetText": "Entrée minimale.", "targetLanguage": "fr-FR"}
    ]
    files = {"file": ("minimal.json", json.dumps(minimal), "application/json")}
    r = await client.post("/api/v1/json/import", files=files, data={"source_system": "minimal-test"})
    assert r.status_code == 200
    unit_id = r.json()["translation_unit_ids"][0]

    export_r = await client.get(f"/api/v1/json/{unit_id}")
    assert export_r.status_code == 200
    unit = export_r.json()["units"][0]
    assert unit["source_text"] == "Bare minimal input."
    assert unit["target_text"] == "Entrée minimale."
    assert unit["provenance"] is not None
    assert unit["provenance"]["bundle_id"]
    assert any(e["entity_type"] == "SourceText" for e in unit["provenance"]["entities"])


@pytest.mark.asyncio
async def test_json_import_malformed_json_400(client):
    files = {"file": ("bad.json", "{not valid json", "application/json")}
    r = await client.post("/api/v1/json/import", files=files, data={"source_system": "bad-test"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_json_import_empty_units_400(client):
    files = {"file": ("empty.json", json.dumps({"units": []}), "application/json")}
    r = await client.post("/api/v1/json/import", files=files, data={"source_system": "empty-test"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_json_export_then_reimport_creates_version_and_revision(client):
    """The full round trip: create -> export -> mutate target text
    externally -> re-import -> a new version row exists, tagged "import",
    and the provenance graph carries a wasRevisionOf edge back to the
    original."""
    payload = {
        "source_text": "Round trip JSON provenance test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "website",
    }
    create_r = await client.post("/api/v1/translations/", json=payload)
    unit_id = create_r.json()["translation_unit_id"]

    export_r = await client.get(f"/api/v1/json/{unit_id}")
    assert export_r.status_code == 200
    doc = export_r.json()
    assert doc["document_id"] == unit_id

    # Simulate an external tool editing the target text, then re-import.
    doc["units"][0]["target_text"] = "Roundtrip-Provenienztest (bearbeitet)."
    files = {"file": ("reimport.json", json.dumps(doc), "application/json")}
    reimport_r = await client.post(
        "/api/v1/json/import", files=files, data={"source_system": "content-provenance-reimport"}
    )
    assert reimport_r.status_code == 200
    assert reimport_r.json()["imported_count"] == 1
    assert reimport_r.json()["translation_unit_ids"][0] == unit_id

    got = await client.get(f"/api/v1/translations/{unit_id}")
    assert got.json()["target_text"] == "Roundtrip-Provenienztest (bearbeitet)."

    prov_r = await client.get(f"/api/v1/provenance/{unit_id}")
    assert prov_r.status_code == 200
    relations = prov_r.json()["provenance"]["relations"]
    assert any(r["type"] == "wasRevisionOf" for r in relations)

    re_export_r = await client.get(f"/api/v1/json/{unit_id}")
    assert re_export_r.status_code == 200
    re_export_unit = re_export_r.json()["units"][0]
    assert re_export_unit["target_text"] == "Roundtrip-Provenienztest (bearbeitet)."
    assert any(r["type"] == "wasRevisionOf" for r in re_export_unit["provenance"]["relations"])


@pytest.mark.asyncio
async def test_json_ingest_log_tracks_both_directions(client):
    payload = {
        "source_text": "JSON ingest ledger test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]
    await client.get(f"/api/v1/json/{unit_id}")  # an "out" event

    r = await client.get("/api/v1/json/ingest-log")
    assert r.status_code == 200
    events = r.json()
    assert any(
        e["direction"] == "out" and e["format"] == "json" and e["xliff_document_id"] == unit_id
        for e in events
    )

    # Shared ledger — the same event set is also visible from the XLIFF-side path.
    xliff_r = await client.get("/api/v1/xliff/ingest-log")
    assert xliff_r.status_code == 200
    assert any(
        e["direction"] == "out" and e["format"] == "json" and e["xliff_document_id"] == unit_id
        for e in xliff_r.json()
    )
