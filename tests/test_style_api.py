"""API-level tests for Phase 13's style/glossary CRUD, retrieval preview,
source-side voice check (app/api/style.py), and TMX import (app/api/tm.py).
Run with: PYTHONPATH=. pytest tests/test_style_api.py -v
"""

import pytest

TMX_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="ApiTestVendor" creationtoolversion="1.0" segtype="sentence"
          o-tmf="ApiTestVendor" adminlang="en-US" srclang="en-US" datatype="plaintext"/>
  <body>
    <tu>
      <tuv xml:lang="en-US"><seg>Sign up today.</seg></tuv>
      <tuv xml:lang="es-ES"><seg>Regístrate hoy.</seg></tuv>
    </tu>
  </body>
</tmx>
"""


@pytest.mark.asyncio
async def test_style_guide_and_rule_and_glossary_crud(client):
    r = await client.post("/api/v1/style/guides", json={
        "name": "API Test Brand Voice", "version": "1.0", "locale": "fr-FR",
        "voice_description": "Warm, upbeat, never robotic.",
        "tone_attributes": {"formality": "casual"},
    })
    assert r.status_code == 201
    guide = r.json()
    assert guide["name"] == "API Test Brand Voice"

    r = await client.get(f"/api/v1/style/guides/{guide['id']}")
    assert r.status_code == 200

    r = await client.post(f"/api/v1/style/guides/{guide['id']}/rules", json={
        "rule_type": "tone", "rule_text": "Always sound upbeat.", "severity": "major",
        "applies_to_locale": "fr-FR",
    })
    assert r.status_code == 201
    rule = r.json()
    assert rule["style_guide_id"] == guide["id"]

    r = await client.get(f"/api/v1/style/guides/{guide['id']}/rules")
    assert r.status_code == 200
    assert any(x["id"] == rule["id"] for x in r.json())

    r = await client.post("/api/v1/style/glossary-terms", json={
        "source_term": "workspace", "target_term": "workstation (deprecated)",
        "locale": "fr-FR", "style_guide_id": guide["id"],
    })
    assert r.status_code == 201
    deprecated_term = r.json()

    r = await client.post("/api/v1/style/glossary-terms", json={
        "source_term": "workstation", "target_term": "poste de travail",
        "locale": "fr-FR", "style_guide_id": guide["id"],
        "preferred_over_term_ids": [deprecated_term["id"]],
    })
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_style_guide_chain_endpoint(client):
    r = await client.post("/api/v1/style/guides", json={"name": "Chain Test", "version": "1.0"})
    v1 = r.json()
    r = await client.post("/api/v1/style/guides", json={
        "name": "Chain Test", "version": "2.0", "supersedes_id": v1["id"],
    })
    v2 = r.json()

    r = await client.get(f"/api/v1/style/guides/{v2['id']}/chain")
    assert r.status_code == 200
    versions = [g["version"] for g in r.json()]
    assert versions == ["2.0", "1.0"]


@pytest.mark.asyncio
async def test_style_guide_not_found_returns_404(client):
    r = await client.get("/api/v1/style/guides/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_retrieve_preview_endpoint(client):
    r = await client.post("/api/v1/style/guides", json={"name": "Retrieve Preview Guide", "locale": "de-DE"})
    guide = r.json()
    await client.post(f"/api/v1/style/guides/{guide['id']}/rules", json={
        "rule_type": "voice", "rule_text": "Sound confident, not salesy.", "applies_to_locale": "de-DE",
    })

    r = await client.get("/api/v1/style/retrieve-preview", params={
        "text": "Buy now!", "source_language": "en-US", "target_language": "de-DE",
        "style_guide_id": guide["id"],
    })
    assert r.status_code == 200
    data = r.json()
    assert any("confident" in fact["text"] for fact in data["rules"])
    assert "confident" in data["prompt_context"]


@pytest.mark.asyncio
async def test_check_source_endpoint_never_500s(client):
    """No ANTHROPIC_API_KEY / anthropic package in this test environment —
    the endpoint must degrade to a needs_review response, never a 500 (see
    app/api/style.py's try/except around scorer.score_text)."""
    r = await client.post("/api/v1/style/check-source", json={
        "text": "Our platform empowers you to synergize workflows.",
        "language": "en-US",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["needs_review"] is True
    assert "scorer_error" in data["reasons"]


@pytest.mark.asyncio
async def test_tmx_import_endpoint(client):
    files = {"file": ("vendor.tmx", TMX_SAMPLE, "application/xml")}
    r = await client.post(
        "/api/v1/tm/import", files=files,
        data={"source_language": "en-US", "target_language": "es-ES", "source_system": "ApiTestVendor"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported_count"] == 1
    assert len(data["exemplar_ids"]) == 1


@pytest.mark.asyncio
async def test_tmx_import_endpoint_rejects_no_matching_pairs(client):
    files = {"file": ("vendor.tmx", TMX_SAMPLE, "application/xml")}
    r = await client.post(
        "/api/v1/tm/import", files=files,
        data={"source_language": "en-US", "target_language": "ja-JP", "source_system": "ApiTestVendor"},
    )
    assert r.status_code == 400
