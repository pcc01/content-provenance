"""
API Integration Tests
Tests the full HTTP request/response cycle for all endpoints.
Run with: PYTHONPATH=. pytest tests/test_api.py -v
"""

import pytest

from app.xliff.xliff_service import PROVX_NS


# ── Translations API ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_create_translation_ai(client):
    payload = {
        "source_text": "Welcome to our platform.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
        "deployment_location": "https://example.com/home",
        "domain": "marketing",
    }
    r = await client.post("/api/v1/translations/", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["source_text"] == payload["source_text"]
    assert data["translation_unit_id"]
    assert data["provenance_record_id"]
    assert data["xliff_document_id"]
    assert data["method"] == "ai"
    return data["translation_unit_id"]


@pytest.mark.asyncio
async def test_create_translation_human(client):
    payload = {
        "source_text": "Click here to learn more.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "human",
        "context": "banner_ad",
        "translator_name": "Jane Smith",
    }
    r = await client.post("/api/v1/translations/", json=payload)
    assert r.status_code == 201
    assert r.json()["method"] == "human"


@pytest.mark.asyncio
async def test_create_translation_hybrid(client):
    payload = {
        "source_text": "Discover our innovative solutions.",
        "source_language": "en-US",
        "target_language": "es-ES",
        "method": "hybrid",
        "context": "marketing_campaign",
        "translator_name": "Post-Editor Pro",
    }
    r = await client.post("/api/v1/translations/", json=payload)
    assert r.status_code == 201
    assert r.json()["method"] == "hybrid"


@pytest.mark.asyncio
async def test_list_translations(client):
    r = await client.get("/api/v1/translations/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_translation(client):
    # Create first
    payload = {
        "source_text": "Test get by ID.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    create_r = await client.post("/api/v1/translations/", json=payload)
    unit_id = create_r.json()["translation_unit_id"]

    # Fetch by ID
    r = await client.get(f"/api/v1/translations/{unit_id}")
    assert r.status_code == 200
    assert r.json()["id"] == unit_id


@pytest.mark.asyncio
async def test_translation_not_found(client):
    r = await client.get("/api/v1/translations/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_record_deployment(client):
    payload = {
        "source_text": "Deployment test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.post(
        f"/api/v1/translations/{unit_id}/deploy",
        params={
            "context": "banner_ad",
            "location": "https://cdn.ads.example.com/fr/banner.html",
            "deployed_by": "campaign-team",
            "version": "v2.1",
        }
    )
    assert r.status_code == 200
    assert r.json()["deployment_id"]


@pytest.mark.asyncio
async def test_mark_reviewed(client):
    payload = {
        "source_text": "Review workflow test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "email",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.put(
        f"/api/v1/translations/{unit_id}/review",
        params={"reviewer_name": "Senior Translator", "quality_score": 94.5}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "reviewed"


@pytest.mark.asyncio
async def test_translation_stats(client):
    r = await client.get("/api/v1/translations/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_translations" in data
    assert "by_method" in data
    assert "total_deployments" in data


# ── Batch lookup + Notes (Phase 5 backend) ──────────────────────────────────

@pytest.mark.asyncio
async def test_translations_batch_lookup(client):
    ids = []
    for text in ["Batch one.", "Batch two."]:
        r = await client.post("/api/v1/translations/", json={
            "source_text": text, "source_language": "en-US", "target_language": "fr-FR",
            "method": "ai", "context": "website",
        })
        ids.append(r.json()["translation_unit_id"])
    ids.append("nonexistent-id")  # must be silently skipped, not error

    r = await client.get("/api/v1/translations/batch", params={"ids": ",".join(ids)})
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 2
    returned_ids = {item["id"] for item in results}
    assert returned_ids == set(ids[:2])
    assert "latest_score" in results[0]


@pytest.mark.asyncio
async def test_translation_versions_endpoint(client):
    payload = {
        "source_text": "Versions endpoint test.", "source_language": "en-US",
        "target_language": "fr-FR", "method": "ai", "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/translations/{unit_id}/versions")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["source_event"] == "initial"

    missing_r = await client.get("/api/v1/translations/does-not-exist/versions")
    assert missing_r.status_code == 404


@pytest.mark.asyncio
async def test_review_notes_thread(client):
    payload = {
        "source_text": "Notes thread test.", "source_language": "en-US",
        "target_language": "fr-FR", "method": "ai", "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    empty_r = await client.get(f"/api/v1/translations/{unit_id}/notes")
    assert empty_r.status_code == 200
    assert empty_r.json() == []

    note_r = await client.post(f"/api/v1/translations/{unit_id}/notes", json={
        "author": "reviewer@example.com", "body": "This reads awkwardly in French.",
    })
    assert note_r.status_code == 201
    note = note_r.json()
    assert note["resolved"] is False

    reply_r = await client.post(f"/api/v1/translations/{unit_id}/notes", json={
        "author": "translator@example.com", "body": "Fixed, please re-check.",
        "parent_id": note["id"],
    })
    assert reply_r.status_code == 201

    list_r = await client.get(f"/api/v1/translations/{unit_id}/notes")
    notes = list_r.json()
    assert len(notes) == 2
    assert notes[1]["parent_id"] == note["id"]

    resolve_r = await client.put(f"/api/v1/translations/{unit_id}/notes/{note['id']}/resolve")
    assert resolve_r.status_code == 200
    assert resolve_r.json()["resolved"] is True


@pytest.mark.asyncio
async def test_notes_reject_unknown_unit(client):
    r = await client.post("/api/v1/translations/does-not-exist/notes", json={
        "author": "someone@example.com", "body": "test",
    })
    assert r.status_code == 404


# ── Provenance API ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_provenance(client):
    payload = {
        "source_text": "Provenance API test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
        "deployment_location": "https://example.com/test",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/provenance/{unit_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["translation_unit_id"] == unit_id
    assert "provenance" in data
    assert len(data["provenance"]["entities"]) >= 2
    assert len(data["provenance"]["activities"]) >= 1
    assert len(data["provenance"]["agents"]) >= 1
    assert len(data["provenance"]["relations"]) > 0


@pytest.mark.asyncio
async def test_get_prov_json(client):
    payload = {
        "source_text": "PROV-JSON test.",
        "source_language": "en-US",
        "target_language": "es-ES",
        "method": "ai",
        "context": "mobile_app",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/provenance/{unit_id}/prov-json")
    assert r.status_code == 200
    data = r.json()
    # W3C PROV-JSON structure
    assert "prefix" in data
    assert "bundle" in data
    assert "prov" in data["prefix"]
    bundle = list(data["bundle"].values())[0]
    assert "entity" in bundle
    assert "activity" in bundle
    assert "agent" in bundle
    assert "wasGeneratedBy" in bundle


@pytest.mark.asyncio
async def test_get_prov_n(client):
    payload = {
        "source_text": "PROV-N notation test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "human",
        "context": "print",
        "translator_name": "Hans Mueller",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/provenance/{unit_id}/prov-n")
    assert r.status_code == 200
    text = r.text
    assert "document" in text
    assert "entity(" in text
    assert "activity(" in text
    assert "agent(" in text
    assert "wasGeneratedBy(" in text
    assert "endDocument" in text


@pytest.mark.asyncio
async def test_get_lineage(client):
    payload = {
        "source_text": "Lineage graph test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "hybrid",
        "context": "social_media",
        "deployment_location": "https://twitter.com/example",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/provenance/{unit_id}/lineage")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 3   # entity, activity, agent minimum
    assert len(data["edges"]) >= 1


@pytest.mark.asyncio
async def test_get_deployments(client):
    payload = {
        "source_text": "Deployments endpoint test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "email",
        "deployment_location": "newsletter-2024-q4",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/provenance/{unit_id}/deployments")
    assert r.status_code == 200
    deployments = r.json()
    assert isinstance(deployments, list)
    assert len(deployments) >= 1
    assert deployments[0]["translation_unit_id"] == unit_id


# ── XLIFF API ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xliff_preview(client):
    payload = {
        "source_text": "XLIFF export test content.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/xliff/{unit_id}/preview")
    assert r.status_code == 200
    xliff = r.json()["xliff"]
    assert '<?xml' in xliff
    assert 'version="2.0"' in xliff
    assert 'XLIFF export test content' in xliff
    assert 'prov' in xliff.lower()


@pytest.mark.asyncio
async def test_xliff_download(client):
    payload = {
        "source_text": "XLIFF download test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "mobile_app",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]

    r = await client.get(f"/api/v1/xliff/{unit_id}")
    assert r.status_code == 200
    assert "xliff" in r.headers.get("content-type", "").lower() or "xml" in r.headers.get("content-type", "").lower()
    assert "attachment" in r.headers.get("content-disposition", "")


# ── XLIFF Import + version history + ingest ledger (Phase 2) ──────────────────

@pytest.mark.asyncio
async def test_xliff_import_new_unit(client):
    """Importing a document with no embedded PROV should still succeed —
    provenance is synthesized (external:{source_system} agent, method
    defaulted to human) rather than the import failing."""
    xml = """<?xml version="1.0"?>
<xliff version="2.0" srcLang="en-US" trgLang="fr-FR"
       xmlns="urn:oasis:names:tc:xliff:document:2.0">
  <file id="ext-file-1">
    <unit id="ext-unit-1">
      <segment state="translated">
        <source>Imported from an external tool.</source>
        <target>Importé depuis un outil externe.</target>
      </segment>
    </unit>
  </file>
</xliff>"""
    files = {"file": ("external.xlf", xml, "application/xliff+xml")}
    r = await client.post("/api/v1/xliff/import", files=files, data={"source_system": "AcmeTMS"})
    assert r.status_code == 200
    data = r.json()
    assert data["imported_count"] == 1
    unit_id = data["translation_unit_ids"][0]

    got = await client.get(f"/api/v1/translations/{unit_id}")
    assert got.status_code == 200
    unit = got.json()
    assert unit["source_text"] == "Imported from an external tool."
    assert unit["target_text"] == "Importé depuis un outil externe."
    assert unit["metadata"]["import_source"] == "AcmeTMS"
    assert unit["metadata"]["method_inferred"] is False


@pytest.mark.asyncio
async def test_xliff_export_then_reimport_creates_version_and_revision(client):
    """The full round trip: create -> export -> mutate target text externally
    -> re-import -> a new version row exists, tagged "import", and the
    provenance graph carries a wasRevisionOf edge back to the original."""
    payload = {
        "source_text": "Round trip provenance test.",
        "source_language": "en-US",
        "target_language": "de-DE",
        "method": "ai",
        "context": "website",
    }
    create_r = await client.post("/api/v1/translations/", json=payload)
    unit_id = create_r.json()["translation_unit_id"]

    export_r = await client.get(f"/api/v1/xliff/{unit_id}")
    assert export_r.status_code == 200
    xml = export_r.text
    assert f'id="{unit_id}"' in xml

    # Simulate an external tool editing the target text, then re-import.
    edited_xml = xml.replace(
        create_r.json()["translated_text"], "Provenienztest der Rundreise (bearbeitet)."
    )
    files = {"file": ("reimport.xlf", edited_xml, "application/xliff+xml")}
    reimport_r = await client.post(
        "/api/v1/xliff/import", files=files, data={"source_system": "content-provenance-reimport"}
    )
    assert reimport_r.status_code == 200
    assert reimport_r.json()["imported_count"] == 1
    assert reimport_r.json()["translation_unit_ids"][0] == unit_id

    got = await client.get(f"/api/v1/translations/{unit_id}")
    assert got.json()["target_text"] == "Provenienztest der Rundreise (bearbeitet)."

    prov_r = await client.get(f"/api/v1/provenance/{unit_id}")
    assert prov_r.status_code == 200
    relations = prov_r.json()["provenance"]["relations"]
    assert any(r["type"] == "wasRevisionOf" for r in relations)

    # The re-export (cache must have been invalidated by the reimport, not
    # served stale) should carry BOTH the formal wasRevisionOf PROV relation
    # and the human-readable per-version notes, and reflect the edited text.
    re_export_r = await client.get(f"/api/v1/xliff/{unit_id}")
    assert re_export_r.status_code == 200
    re_export_xml = re_export_r.text
    assert "Provenienztest der Rundreise (bearbeitet)." in re_export_xml
    assert "wasRevisionOf" in re_export_xml
    assert f"{PROVX_NS}:version" in re_export_xml
    assert "sourceEvent=import" in re_export_xml
    assert re_export_xml.count(f'category="{PROVX_NS}:version"') == 2  # initial + import


@pytest.mark.asyncio
async def test_ingest_log_tracks_both_directions(client):
    payload = {
        "source_text": "Ingest ledger test.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    unit_id = (await client.post("/api/v1/translations/", json=payload)).json()["translation_unit_id"]
    await client.get(f"/api/v1/xliff/{unit_id}")  # an "out" event

    r = await client.get("/api/v1/xliff/ingest-log")
    assert r.status_code == 200
    events = r.json()
    assert any(e["direction"] == "out" and e["xliff_document_id"] == unit_id for e in events)


# ── Redrive API (Phase 3) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redrive_run_and_queue_via_api(client):
    """Exercises the real HTTP endpoints with the default (claude) scoring
    provider, but only through a case the deterministic pre-check resolves
    on its own (target forced identical to source) — so this validates the
    API contract without needing a real Claude API key configured."""
    payload = {
        "source_text": "API redrive test content.",
        "source_language": "en-US",
        "target_language": "es-ES",
        "method": "ai",
        "context": "website",
    }
    create_r = await client.post("/api/v1/translations/", json=payload)
    unit_id = create_r.json()["translation_unit_id"]

    export_xml = (await client.get(f"/api/v1/xliff/{unit_id}")).text
    translated = create_r.json()["translated_text"]
    bad_xml = export_xml.replace(translated, payload["source_text"])  # simulate untranslated content
    reimport_r = await client.post(
        "/api/v1/xliff/import",
        files={"file": ("bad.xlf", bad_xml, "application/xliff+xml")},
        data={"source_system": "redrive-test-setup"},
    )
    assert reimport_r.status_code == 200

    run_r = await client.post("/api/v1/redrive/runs", json={
        "threshold": 50, "scope": {"unit_ids": [unit_id]},
    })
    assert run_r.status_code == 200
    run = run_r.json()
    assert run["status"] == "completed"
    assert run["summary"]["redriven"] == 1
    assert run["items"][0]["before_score"] == 0
    assert run["items"][0]["outcome"] == "redriven"

    got_r = await client.get(f"/api/v1/redrive/runs/{run['id']}")
    assert got_r.status_code == 200
    assert got_r.json()["status"] == "completed"

    unit_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_r.json()["target_text"] != payload["source_text"]

    queue_r = await client.get("/api/v1/redrive/queue", params={"threshold": 100, "target_language": "es-ES"})
    assert queue_r.status_code == 200
    # After redrive the unit no longer scores 0/untranslated deterministically,
    # so with a low bar it may or may not still appear — just check the shape.
    assert isinstance(queue_r.json(), list)


@pytest.mark.asyncio
async def test_redrive_human_in_the_loop_via_api(client):
    payload = {
        "source_text": "HITL API test content.",
        "source_language": "en-US",
        "target_language": "it-IT",
        "method": "ai",
        "context": "website",
    }
    create_r = await client.post("/api/v1/translations/", json=payload)
    unit_id = create_r.json()["translation_unit_id"]

    export_xml = (await client.get(f"/api/v1/xliff/{unit_id}")).text
    translated = create_r.json()["translated_text"]
    bad_xml = export_xml.replace(translated, payload["source_text"])
    await client.post(
        "/api/v1/xliff/import",
        files={"file": ("bad.xlf", bad_xml, "application/xliff+xml")},
        data={"source_system": "hitl-test-setup"},
    )

    run_r = await client.post("/api/v1/redrive/runs", json={
        "threshold": 50, "scope": {"unit_ids": [unit_id]}, "require_human_approval": True,
    })
    assert run_r.status_code == 200
    run = run_r.json()
    assert run["summary"]["pending_approval"] == 1
    item = run["items"][0]
    assert item["outcome"] == "pending_approval"
    assert item["proposed_text"]

    # Must not have applied yet.
    unit_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_r.json()["target_text"] == payload["source_text"]

    approve_r = await client.post(
        f"/api/v1/redrive/runs/{run['id']}/items/{item['id']}/approve",
        json={"actor": "qa-lead@example.com"},
    )
    assert approve_r.status_code == 200
    assert approve_r.json()["outcome"] == "redriven"
    assert approve_r.json()["approved_by"] == "qa-lead@example.com"

    unit_after_r = await client.get(f"/api/v1/translations/{unit_id}")
    assert unit_after_r.json()["target_text"] != payload["source_text"]

    # Approving an already-resolved item must fail cleanly.
    reapprove_r = await client.post(
        f"/api/v1/redrive/runs/{run['id']}/items/{item['id']}/approve",
        json={"actor": "someone-else@example.com"},
    )
    assert reapprove_r.status_code == 400


# ── Search API ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_basic(client):
    # Seed a translation
    await client.post("/api/v1/translations/", json={
        "source_text": "Searchable content about machine learning.",
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    })

    r = await client.get("/api/v1/search/", params={"q": "machine learning", "semantic": False})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "total" in data
    assert "search_type" in data


@pytest.mark.asyncio
async def test_search_with_filters(client):
    r = await client.get("/api/v1/search/", params={
        "q": "platform",
        "method": "ai",
        "semantic": False,
        "top_k": 5,
    })
    assert r.status_code == 200
    data = r.json()
    for result in data["results"]:
        assert result["translation_method"] == "ai"


@pytest.mark.asyncio
async def test_indexed_count(client):
    r = await client.get("/api/v1/search/indexed-count")
    assert r.status_code == 200
    assert "indexed_documents" in r.json()
