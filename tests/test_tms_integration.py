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

    async def fetch_approved_translation(self, *, key, language):
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


# ── /webhook ────────────────────────────────────────────────────────────

async def test_webhook_applies_approved_translation(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    unit_id = await _create_unit(client, "Webhook approval content.")
    ev = TMSApprovalEvent(key=unit_id, language="fr", approved_text="Contenu approuvé.", translator="bob")
    monkeypatch.setattr("app.api.tms.get_tms_integration", lambda provider=None: _StubTMS(event=ev))

    r = await client.post("/api/v1/integrations/tms/webhook?secret=s3cr3t", json={"event": "suggestion.approved"})
    assert r.status_code == 200
    assert r.json()["applied"] is True and r.json()["unit_id"] == unit_id

    unit = (await client.get(f"/api/v1/translations/{unit_id}")).json()
    assert unit["target_text"] == "Contenu approuvé."
    assert unit["translation_method"] == "hybrid" and unit["status"] == "reviewed"

    versions = (await client.get(f"/api/v1/translations/{unit_id}/versions")).json()
    assert versions[-1]["source_event"] == "tms_review"
    assert "bob" in (versions[-1]["note"] or "")

    log = (await client.get("/api/v1/xliff/ingest-log")).json()
    assert any(e["direction"] == "in" and e["format"] == "crowdin" for e in log)


async def test_webhook_bad_secret_401(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    unit_id = await _create_unit(client)
    ev = TMSApprovalEvent(key=unit_id, language="fr", approved_text="X.")
    monkeypatch.setattr("app.api.tms.get_tms_integration", lambda provider=None: _StubTMS(event=ev))

    r = await client.post("/api/v1/integrations/tms/webhook?secret=wrong", json={})
    assert r.status_code == 401
    unit = (await client.get(f"/api/v1/translations/{unit_id}")).json()
    assert unit["target_text"].startswith("[FR]")  # untouched


async def test_webhook_unknown_key_noop(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    ev = TMSApprovalEvent(key="not-a-real-unit", language="fr", approved_text="X.")
    monkeypatch.setattr("app.api.tms.get_tms_integration", lambda provider=None: _StubTMS(event=ev))
    r = await client.post("/api/v1/integrations/tms/webhook?secret=s3cr3t", json={})
    assert r.status_code == 200 and r.json()["applied"] is False


async def test_webhook_ignored_event(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    monkeypatch.setattr("app.api.tms.get_tms_integration", lambda provider=None: _StubTMS(event=None))
    r = await client.post("/api/v1/integrations/tms/webhook?secret=s3cr3t", json={"event": "string.added"})
    assert r.status_code == 200 and r.json()["applied"] is False


async def test_webhook_signature_mismatch_400(client, monkeypatch):
    _configure_crowdin(monkeypatch)
    monkeypatch.setattr(
        "app.api.tms.get_tms_integration", lambda provider=None: _StubTMS(raise_on_parse=True),
    )
    r = await client.post("/api/v1/integrations/tms/webhook?secret=s3cr3t", json={})
    assert r.status_code == 400


# ── /pull ───────────────────────────────────────────────────────────────

async def test_pull_applies_approved_translation(client, monkeypatch):
    unit_id = await _create_unit(client, "Poll approval content.")
    stub = _StubTMS(approved_text="Traduction validée.")
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: stub)

    r = await client.get(f"/api/v1/integrations/tms/pull?unit_id={unit_id}")
    assert r.status_code == 200 and r.json()["applied"] is True
    unit = (await client.get(f"/api/v1/translations/{unit_id}")).json()
    assert unit["target_text"] == "Traduction validée."


async def test_pull_no_approval_yet(client, monkeypatch):
    unit_id = await _create_unit(client)
    monkeypatch.setattr(
        "app.core.tms_service.get_tms_integration", lambda provider=None: _StubTMS(approved_text=None),
    )
    r = await client.get(f"/api/v1/integrations/tms/pull?unit_id={unit_id}")
    assert r.status_code == 200 and r.json()["applied"] is False


async def test_pull_missing_unit_404(client, monkeypatch):
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: _StubTMS())
    r = await client.get("/api/v1/integrations/tms/pull?unit_id=nope")
    assert r.status_code == 404


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


# ── redrive routing: a `human` bucket -> Crowdin ───────────────────────

def _redrive_engine():
    from app.core.redrive.engine import RedriveEngine
    from app.core.translation_backends import MockTranslationBackend
    from tests.test_quality_reports import _MarkerScorer
    return RedriveEngine(
        scorer=_MarkerScorer(), scorer_label="stub-judge",
        redrive_backend=MockTranslationBackend(), redrive_label="mock",
    )


async def test_redrive_human_route_to_crowdin_sends_instead_of_pending(client, monkeypatch):
    from app.core.database import get_db, init_db
    from app.models.schemas import RecommendedAction, RedriveRouting, RoutingTarget
    from tests.test_quality_reports import _mk_unit

    await init_db()
    db = get_db()
    stub = _StubTMS()
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", lambda provider=None: stub)

    unit = await _mk_unit(db, "low")  # -> below_quality
    report = await _redrive_engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)
    run = await _redrive_engine().redrive_from_report(
        report,
        RedriveRouting(by_bucket={
            "below_quality": RoutingTarget(action=RecommendedAction.HUMAN, review_venue="crowdin"),
        }),
    )

    item = run.items[0]
    assert item.outcome.value == "sent_to_tms"
    assert "crowdin" in item.detail
    assert stub.strings and stub.strings[0]["key"] == unit.id
    assert stub.suggestions and stub.suggestions[0]["text"].startswith("[FR]")  # the fresh redrive draft
    # nothing left in the in-app pending queue for this unit
    assert await db.list_pending_redrive_items_for_units([unit.id]) == []


async def test_redrive_crowdin_route_falls_back_when_unconfigured(client, monkeypatch):
    from app.core.database import get_db, init_db
    from app.models.schemas import RecommendedAction, RedriveRouting, RoutingTarget
    from tests.test_quality_reports import _mk_unit

    await init_db()
    db = get_db()

    def _raise(provider=None):
        raise ValueError("Crowdin integration is not configured")
    monkeypatch.setattr("app.core.tms_service.get_tms_integration", _raise)

    unit = await _mk_unit(db, "low")
    report = await _redrive_engine().evaluate(scope={"unit_ids": [unit.id]}, quality_threshold=80)
    run = await _redrive_engine().redrive_from_report(
        report,
        RedriveRouting(by_bucket={
            "below_quality": RoutingTarget(action=RecommendedAction.HUMAN, review_venue="crowdin"),
        }),
    )

    item = run.items[0]
    assert item.outcome.value == "pending_approval"
    assert "TMS unavailable" in item.detail
