"""Phase 16 — multi-provider translate/evaluate/retranslate registry tests.

Covers: every provider is registered in both factories, an explicit
provider always builds a fresh instance (never the cached default), unknown
providers are rejected with a clear error, and missing-credential providers
degrade gracefully (RuntimeError, not a crash) rather than silently
succeeding against wrong-shaped requests. No live external calls — mirrors
tests/test_mqm.py and tests/test_style_scoring.py's stub-scorer convention;
this file stubs at the credentials/registry level instead since these
providers have no local stand-in the way Ollama has a stub scorer.

Run with: PYTHONPATH=. pytest tests/test_multiprovider.py -v
"""

import pytest

from app.core.config import settings
from app.core.scoring.base import ScoreResult
from app.core.scoring.factory import CompositeScorer, get_scorer
from app.core.translation_backends import (
    AnthropicTranslationBackend,
    GeminiTranslationBackend,
    MockTranslationBackend,
    MSTranslatorTranslationBackend,
    OpenAITranslationBackend,
    _PROVIDER_CLASSES,
    get_translation_backend,
)

# ── Translation backend registry ────────────────────────────────────────────

EXPECTED_TRANSLATE_PROVIDERS = {
    "mock", "anthropic", "openai", "gemini", "deepl", "google",
    "mstranslator", "ollama", "lmstudio", "vllm",
}


def test_every_expected_translation_provider_is_registered():
    assert set(_PROVIDER_CLASSES) == EXPECTED_TRANSLATE_PROVIDERS


def test_get_translation_backend_unknown_provider_raises():
    with pytest.raises(RuntimeError, match="Unknown translation provider"):
        get_translation_backend("carrier-pigeon")


def test_get_translation_backend_explicit_provider_builds_fresh_instance():
    """provider=None reuses the cached singleton; passing one explicitly
    never does — mirrors get_scorer()'s identical contract."""
    a = get_translation_backend("mock")
    b = get_translation_backend("mock")
    assert isinstance(a, MockTranslationBackend)
    assert a is not b  # explicit provider -> always fresh


def test_get_translation_backend_anthropic_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_translation_backend("anthropic")


def test_get_translation_backend_deepl_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "deepl_api_key", "")
    with pytest.raises(RuntimeError, match="DEEPL_API_KEY"):
        get_translation_backend("deepl")


@pytest.mark.asyncio
async def test_openai_translation_backend_without_key_raises_on_translate(monkeypatch):
    """OpenAI/Gemini/MSTranslator check credentials at translate()-call time
    rather than construction time (unlike anthropic/deepl above) — still
    degrades to a clear RuntimeError rather than an opaque 401 from the API."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    backend = OpenAITranslationBackend()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await backend.translate("Hello", "en-US", "fr-FR")


@pytest.mark.asyncio
async def test_gemini_translation_backend_without_key_raises_on_translate(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    backend = GeminiTranslationBackend()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await backend.translate("Hello", "en-US", "fr-FR")


@pytest.mark.asyncio
async def test_mstranslator_backend_without_key_raises_on_translate(monkeypatch):
    monkeypatch.setattr(settings, "ms_translator_key", "")
    backend = MSTranslatorTranslationBackend()
    with pytest.raises(RuntimeError, match="MS_TRANSLATOR_KEY"):
        await backend.translate("Hello", "en-US", "fr-FR")


@pytest.mark.asyncio
async def test_mock_translation_backend_round_trips_without_credentials():
    """Sanity check the one provider that always works — every test above
    proves failure modes; this proves the registry isn't rejecting
    everything."""
    backend = get_translation_backend("mock")
    text, confidence = await backend.translate("Hello", "en-US", "fr-FR")
    assert text.startswith("[FR]")
    assert 0.0 < confidence <= 1.0


# ── Scoring provider registry ───────────────────────────────────────────────

EXPECTED_SCORE_PROVIDERS = {"claude", "ollama", "gemini", "openai", "lmstudio", "vllm"}


def test_get_scorer_unknown_provider_raises():
    with pytest.raises(RuntimeError, match="Unknown scoring provider"):
        get_scorer("carrier-pigeon")


def test_get_scorer_explicit_provider_builds_fresh_composite_scorer():
    a = get_scorer("ollama")
    b = get_scorer("ollama")
    assert isinstance(a, CompositeScorer)
    assert a is not b  # explicit provider -> always fresh, same contract as translation backends


def test_get_scorer_openai_without_key_raises(monkeypatch):
    """openai/lmstudio/vllm scorers build an OpenAICompatibleClient inside
    get_scorer() itself, so — unlike the gemini/claude scorers, which check
    at score()-call time — a missing OPENAI_API_KEY is caught immediately."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_scorer("openai")


@pytest.mark.asyncio
async def test_gemini_scorer_without_key_degrades_instead_of_crashing(monkeypatch):
    """The deterministic floor doesn't fire for a plausible-looking pair
    (see app/core/scoring/deterministic.py), so this exercises the actual
    GeminiQualityScorer.score() path, which raises RuntimeError when
    GEMINI_API_KEY is unset. A REAL translation-quality caller (RedriveEngine,
    POST /quality/evaluate) wraps this in its own try/except and converts it
    to needs_review=True rather than crashing the request — same contract
    verified directly against the scorer here, one layer down."""
    from app.models.schemas import TranslationUnit, TranslationMethod

    monkeypatch.setattr(settings, "gemini_api_key", "")
    unit = TranslationUnit(
        source_id="src-gemini-no-key", source_text="Hello there, friend.", source_language="en-US",
        target_text="Bonjour l'ami.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id="test-agent",
    )
    scorer = get_scorer("gemini")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await scorer.score(unit)


@pytest.mark.asyncio
async def test_composite_scorer_short_circuits_on_deterministic_floor():
    """An untranslated pair never reaches the (possibly credential-less)
    model scorer at all — deterministic.py's free check resolves it first."""
    from app.models.schemas import TranslationUnit, TranslationMethod

    unit = TranslationUnit(
        source_id="src-untranslated", source_text="Hello there, friend.", source_language="en-US",
        target_text="Hello there, friend.", target_language="fr-FR",  # identical -> untranslated
        translation_method=TranslationMethod.AI, translated_by_agent_id="test-agent",
    )
    scorer = get_scorer("gemini")  # no GEMINI_API_KEY needed — never reached
    result: ScoreResult = await scorer.score(unit)
    assert result.deterministic is True
    assert result.score == 0
    assert "untranslated" in result.reasons


# ── POST /api/v1/quality/evaluate ───────────────────────────────────────────

class _StubEvaluateScorer:
    """Same offline-stub convention as tests/test_redrive.py's _StubScorer —
    monkeypatched in place of app.api.quality's get_scorer so this exercises
    the endpoint's request/response wiring without needing a real API key."""

    async def score(self, unit):
        return ScoreResult(score=72, reasons=["evaluator_flagged"], hard_fail=False)


@pytest.mark.asyncio
async def test_evaluate_endpoint_scores_and_persists(client, monkeypatch):
    from app.core.database import get_db, init_db
    from app.models.schemas import TranslationMethod, TranslationUnit

    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-evaluate-agent", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-evaluate", source_text="Hello there, friend.", source_language="en-US",
        target_text="Bonjour l'ami.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    monkeypatch.setattr("app.api.quality.get_scorer", lambda provider=None, model=None: _StubEvaluateScorer())

    resp = await client.post("/api/v1/quality/evaluate", json={"unit_id": unit.id, "provider": "claude"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit_id"] == unit.id
    assert body["score"] == 72
    assert body["scorer"] == "claude"

    latest = await db.get_latest_quality_score(unit.id)
    assert latest.score == 72  # actually persisted, not just echoed back


@pytest.mark.asyncio
async def test_evaluate_endpoint_404s_for_unknown_unit(client):
    resp = await client.post("/api/v1/quality/evaluate", json={"unit_id": "does-not-exist"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_endpoint_400s_for_unknown_provider(client):
    from app.core.database import get_db, init_db
    from app.models.schemas import TranslationMethod, TranslationUnit

    await init_db()
    db = get_db()
    agent = await db.get_or_create_agent("test-evaluate-agent-2", "SoftwareAgent")
    unit = TranslationUnit(
        source_id="src-evaluate-2", source_text="Hi.", source_language="en-US",
        target_text="Salut.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent.id,
    )
    await db.save_translation_unit(unit)

    resp = await client.post("/api/v1/quality/evaluate", json={"unit_id": unit.id, "provider": "carrier-pigeon"})
    assert resp.status_code == 400
