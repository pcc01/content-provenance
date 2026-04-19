"""
API Integration Tests
Tests the full HTTP request/response cycle for all endpoints.
Run with: PYTHONPATH=. pytest tests/test_api.py -v
"""

import pytest


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
