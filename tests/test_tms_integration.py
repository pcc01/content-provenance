"""
TMS Integration (Crowdin) tests — offline-stub convention, mirroring
tests/test_cms_integration.py: monkeypatch get_tms_integration in place so
the endpoint wiring + provenance bookkeeping are exercised without a real
Crowdin project.

Run with: PYTHONPATH=. pytest tests/test_tms_integration.py -v
"""

import pytest

from app.core.config import settings
from app.core.integrations.base import TMSApprovalEvent
from app.core.integrations.crowdin import crowdin_lang

pytestmark = pytest.mark.asyncio


class _StubTMS:
    """Records every call so tests can assert exactly what would reach Crowdin."""

    provider = "crowdin"

    def __init__(self, *, approved_text=None, event=None, raise_on_parse=False):
        self.strings = []
        self.suggestions = []
        self.comments = []
        self.webhooks = []
        self._approved_text = approved_text
        self._event = event
        self._raise_on_parse = raise_on_parse

    async def upsert_source_string(self, *, key, text, context=None, max_length=None):
        self.strings.append({"key": key, "text": text, "context": context})
        return {"string_id": f"str-{key[:8]}", "created": True, "raw": {}}

    async def add_suggestion(self, *, string_id, language, text):
        self.suggestions.append({"string_id": string_id, "language": language, "text": text})
        return {}

    async def add_comment(self, *, string_id, text):
        self.comments.append({"string_id": string_id, "text": text})
        return {}

    async def fetch_approved_translation(self, *, string_id, language):
        return self._approved_text

    async def ensure_webhook(self, *, callback_url, events):
        self.webhooks.append({"callback_url": callback_url, "events": events})
        return {"webhook_id": "wh-1", "created": True}

    def parse_webhook_event(self, headers, body, secret):
        if self._raise_on_parse:
            raise ValueError("Crowdin webhook signature mismatch")
        return self._event


async def _create_unit(client, source_text="TMS review test content."):
    r = await client.post("/api/v1/translations/", json={
        "source_text": source_text, "source_language": "en-US",
        "target_language": "fr-FR", "method": "ai", "context": "website",
    })
    return r.json()["translation_unit_id"]


def _configure_crowdin(monkeypatch):
    monkeypatch.setattr(settings, "tms_provider", "crowdin")
    monkeypatch.setattr(settings, "crowdin_project_id", "12345")
    monkeypatch.setattr(settings, "crowdin_api_token", "test-token")
    monkeypatch.setattr(settings, "crowdin_webhook_secret", "s3cr3t")


# ── /send ────────────────────────────────────────────────────────────────

async def test_send_pushes_string_suggestion_and_comment(client, monkeypatch):
    stub = _StubTMS()
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: stub)
    unit_id = await _create_unit(client)

    r = await client.post("/api/v1/integrations/tms/send", json={"unit_id": unit_id})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "crowdin"
    assert body["suggestion_added"] is True
    assert body["comment_added"] is True

    assert len(stub.strings) == 1 and stub.strings[0]["key"] == unit_id
    assert stub.suggestions[0]["language"] == "fr-FR"
    assert stub.suggestions[0]["text"].startswith("[FR]")
    assert "Content Provenance" in stub.comments[0]["text"]

    log = (await client.get("/api/v1/xliff/ingest-log")).json()
    assert any(e["direction"] == "out" and e["format"] == "crowdin" for e in log)


async def test_send_can_skip_draft_and_note(client, monkeypatch):
    stub = _StubTMS()
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: stub)
    unit_id = await _create_unit(client)

    r = await client.post("/api/v1/integrations/tms/send", json={
        "unit_id": unit_id, "include_mt_draft": False, "include_quality_note": False,
    })
    assert r.status_code == 200
    assert stub.suggestions == [] and stub.comments == []


async def test_send_missing_unit_404(client, monkeypatch):
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: _StubTMS())
    r = await client.post("/api/v1/integrations/tms/send", json={"unit_id": "nope"})
    assert r.status_code == 404


async def test_send_unconfigured_400(client, monkeypatch):
    monkeypatch.setattr(settings, "crowdin_project_id", "")
    monkeypatch.setattr(settings, "crowdin_api_token", "")
    unit_id = await _create_unit(client)
    r = await client.post("/api/v1/integrations/tms/send", json={"unit_id": unit_id})
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"].lower()


# ── /setup-webhook + /status ────────────────────────────────────────────

async def test_setup_webhook_registers_events(client, monkeypatch):
    stub = _StubTMS()
    monkeypatch.setattr("app.api.tms.get_tms_integration", lambda provider=None: stub)
    r = await client.post("/api/v1/integrations/tms/setup-webhook", json={
        "callback_url": "https://example.com/api/v1/integrations/tms/webhook?secret=s3cr3t",
    })
    assert r.status_code == 200
    assert r.json()["events"] == ["suggestion.approved"]
    assert stub.webhooks[0]["events"] == ["suggestion.approved"]


async def test_setup_webhook_requires_url(client):
    r = await client.post("/api/v1/integrations/tms/setup-webhook", json={})
    assert r.status_code == 400


async def test_status_configured(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    r = await client.get("/api/v1/integrations/tms/status")
    assert r.status_code == 200
    body = r.json()
    assert body == {"provider": "crowdin", "configured": True, "project_id": "12345", "detail": None}


async def test_status_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "tms_provider", "crowdin")
    monkeypatch.setattr(settings, "crowdin_project_id", "")
    monkeypatch.setattr(settings, "crowdin_api_token", "")
    r = await client.get("/api/v1/integrations/tms/status")
    assert r.json()["configured"] is False


# ── crowdin_lang mapping ────────────────────────────────────────────────

def test_crowdin_lang_mapping():
    assert crowdin_lang("fr-FR") == "fr"
    assert crowdin_lang("de-DE") == "de"
    assert crowdin_lang("pt-BR") == "pt-BR"      # regional kept
    assert crowdin_lang("zh-CN") == "zh-CN"
    assert crowdin_lang("es") == "es"


# ── webhook parsing (unit-level, no HTTP) ───────────────────────────────

def test_crowdin_parse_webhook_extracts_approval():
    from app.core.integrations.crowdin import CrowdinIntegration
    integ = CrowdinIntegration("https://api.crowdin.com/api/v2", "1", "tok")
    body = (
        b'{"events":[{"event":"suggestion.approved","suggestion":{'
        b'"text":"Bonjour","targetLanguage":{"id":"fr"},'
        b'"string":{"identifier":"unit-abc"},"user":{"username":"alice"}}}]}'
    )
    ev = integ.parse_webhook_event({}, body, "s3cr3t")
    assert isinstance(ev, TMSApprovalEvent)
    assert ev.key == "unit-abc" and ev.approved_text == "Bonjour"
    assert ev.language == "fr" and ev.translator == "alice"


def test_crowdin_parse_webhook_ignores_other_events():
    from app.core.integrations.crowdin import CrowdinIntegration
    integ = CrowdinIntegration("https://api.crowdin.com/api/v2", "1", "tok")
    assert integ.parse_webhook_event({}, b'{"event":"string.added","string":{}}', "x") is None
