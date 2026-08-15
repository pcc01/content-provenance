"""
CMS Integration API Tests — Strapi push/pull, mirroring the offline-stub
convention tests/test_multiprovider.py and tests/test_redrive.py already
use for scorer/backend factories: monkeypatch the factory function in
place, exercising the endpoint's request/response wiring and provenance
bookkeeping without needing a real Strapi instance.

Run with: PYTHONPATH=. pytest tests/test_cms_integration.py -v
"""

import pytest

from app.core.config import settings


class _StubCMSIntegration:
    """Records every call so tests can assert on exactly what would have
    been sent to the real CMS."""

    provider = "strapi"

    def __init__(self, pull_value="Pulled source text from CMS."):
        self.pushed = []
        self.pulled = []
        self._pull_value = pull_value

    async def push_field(self, content_type, entry_id, field, value, locale=None, extra_fields=None):
        self.pushed.append({
            "content_type": content_type, "entry_id": entry_id, "field": field,
            "value": value, "locale": locale, "extra_fields": extra_fields,
        })
        return {"data": {"id": entry_id, field: value}}

    async def pull_field(self, content_type, entry_id, field, locale=None):
        self.pulled.append({
            "content_type": content_type, "entry_id": entry_id, "field": field, "locale": locale,
        })
        return self._pull_value


async def _create_unit(client, source_text="CMS push test content."):
    payload = {
        "source_text": source_text,
        "source_language": "en-US",
        "target_language": "fr-FR",
        "method": "ai",
        "context": "website",
    }
    r = await client.post("/api/v1/translations/", json=payload)
    return r.json()["translation_unit_id"]


# ── Push ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cms_push_writes_field_and_provenance(client, monkeypatch):
    stub = _StubCMSIntegration()
    monkeypatch.setattr("app.core.cms_service.get_cms_integration", lambda provider=None: stub)

    unit_id = await _create_unit(client)
    r = await client.post("/api/v1/integrations/cms/push", json={
        "unit_id": unit_id, "provider": "strapi", "content_type": "articles",
        "entry_id": "42", "field_name": "body", "locale": "fr",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "strapi"
    assert body["deployment_id"]
    assert body["provenance_field"] == settings.cms_provenance_field

    assert len(stub.pushed) == 1
    call = stub.pushed[0]
    assert call["content_type"] == "articles"
    assert call["entry_id"] == "42"
    assert call["field"] == "body"
    assert call["locale"] == "fr"
    prov_payload = call["extra_fields"][settings.cms_provenance_field]
    assert prov_payload["bundle_id"]
    assert prov_payload["entities"]

    # The push created a context=cms DeploymentRecord, and the unit's
    # provenance was rebuilt to include it.
    deps_r = await client.get(f"/api/v1/provenance/{unit_id}/deployments")
    assert deps_r.status_code == 200
    deployments = deps_r.json()
    assert any(d["context"] == "cms" and d["location"] == "strapi:articles:42:fr" for d in deployments)

    prov_r = await client.get(f"/api/v1/provenance/{unit_id}")
    assert any(e["entity_type"] == "DeployedContent" for e in prov_r.json()["provenance"]["entities"])


@pytest.mark.asyncio
async def test_cms_push_missing_unit_404(client, monkeypatch):
    monkeypatch.setattr("app.core.cms_service.get_cms_integration", lambda provider=None: _StubCMSIntegration())
    r = await client.post("/api/v1/integrations/cms/push", json={
        "unit_id": "does-not-exist", "provider": "strapi", "content_type": "articles",
        "entry_id": "42", "field_name": "body",
    })
    assert r.status_code == 404


# ── Pull ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cms_pull_returns_fetched_text(client, monkeypatch):
    stub = _StubCMSIntegration(pull_value="Source text fetched from Strapi.")
    monkeypatch.setattr("app.core.cms_service.get_cms_integration", lambda provider=None: stub)

    r = await client.get("/api/v1/integrations/cms/pull", params={
        "provider": "strapi", "content_type": "articles", "entry_id": "42",
        "field_name": "body", "locale": "en",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["source_text"] == "Source text fetched from Strapi."
    assert body["source_id"] == "strapi:articles:42:body:en"
    assert stub.pulled == [{"content_type": "articles", "entry_id": "42", "field": "body", "locale": "en"}]


@pytest.mark.asyncio
async def test_cms_pull_not_found_404(client, monkeypatch):
    stub = _StubCMSIntegration(pull_value=None)
    monkeypatch.setattr("app.core.cms_service.get_cms_integration", lambda provider=None: stub)

    r = await client.get("/api/v1/integrations/cms/pull", params={
        "provider": "strapi", "content_type": "articles", "entry_id": "999", "field_name": "body",
    })
    assert r.status_code == 404


# ── Configuration / provider errors ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_cms_status_reports_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "strapi_base_url", "")
    monkeypatch.setattr(settings, "strapi_api_token", "")
    r = await client.get("/api/v1/integrations/cms/status", params={"provider": "strapi"})
    assert r.status_code == 200
    assert r.json()["configured"] is False


@pytest.mark.asyncio
async def test_cms_push_unconfigured_strapi_400(client, monkeypatch):
    monkeypatch.setattr(settings, "strapi_base_url", "")
    monkeypatch.setattr(settings, "strapi_api_token", "")
    unit_id = await _create_unit(client, source_text="Unconfigured Strapi test.")

    r = await client.post("/api/v1/integrations/cms/push", json={
        "unit_id": unit_id, "provider": "strapi", "content_type": "articles",
        "entry_id": "1", "field_name": "body",
    })
    assert r.status_code == 400
    assert "STRAPI_BASE_URL" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cms_directus_not_implemented_400(client):
    unit_id = await _create_unit(client, source_text="Directus not-implemented test.")
    r = await client.post("/api/v1/integrations/cms/push", json={
        "unit_id": unit_id, "provider": "directus", "content_type": "articles",
        "entry_id": "1", "field_name": "body",
    })
    assert r.status_code == 400
    assert "not implemented yet" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cms_unknown_provider_400(client):
    unit_id = await _create_unit(client, source_text="Unknown provider test.")
    r = await client.post("/api/v1/integrations/cms/push", json={
        "unit_id": unit_id, "provider": "bogus-cms", "content_type": "articles",
        "entry_id": "1", "field_name": "body",
    })
    assert r.status_code == 400
    assert "Unknown CMS provider" in r.json()["detail"]
