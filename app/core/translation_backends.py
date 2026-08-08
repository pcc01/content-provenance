"""
Translation Backend Abstraction Layer
Supports mock, Anthropic Claude, OpenAI, Google Gemini, DeepL, Google
Translate, Microsoft Translator, Ollama, LMStudio, and vLLM.

Default provider is TRANSLATION_PROVIDER (env var); every provider is also
selectable per-request (Phase 16) via get_translation_backend(provider=...)
— see TranslateRequest.provider / RedriveRunRequest.redrive_provider,
which is the actual "surfaced in the UI" requirement: choosing a provider
is no longer a process-wide, restart-to-change setting.
"""

from typing import Optional, Tuple

from app.core.config import settings
from app.core.llm_clients import GeminiClient, MSTranslatorClient, OpenAICompatibleClient


# ── Base interface ─────────────────────────────────────────────────────────────

class TranslationBackend:
    """Abstract translation backend. Implement translate() for each provider.

    style_context (Phase 13): a compact, pre-rendered block of retrieved
    style-guide rules / glossary terms / prior-translation exemplars (see
    app.core.graph.retrieval.retrieve_style_context and
    StyleContextRetrieval.as_prompt_context) — grounds the translation in
    brand voice/terminology instead of scoring it after the fact. Honored
    by every chat-completion-capable backend (Anthropic/OpenAI/Gemini/
    Ollama/LMStudio/vLLM); ignored by the pure-NMT ones (DeepL, Google
    Translate, MS Translator), which have no instruction-following
    channel to hand it to.
    """

    async def translate(
        self, text: str, source_lang: str, target_lang: str, domain: str = None,
        style_context: str = None,
    ) -> Tuple[str, float]:
        """
        Returns (translated_text, confidence_score 0.0–1.0).
        """
        raise NotImplementedError


def _chat_translate_prompt(text: str, source_lang: str, target_lang: str, domain: Optional[str], style_context: Optional[str]) -> Tuple[str, str]:
    """Shared (system, user) prompt pair for every chat-completion-style
    backend — one prompt definition instead of five drifting copies."""
    system = (
        "You are a professional translator. Translate the provided text accurately and naturally.\n"
        "Preserve formatting, tone, and meaning. Do not add explanations or commentary — return only the translation.\n"
        "If style/voice/glossary context is supplied, follow it — it reflects the target brand's approved "
        "terminology and tone, and takes precedence over your own stylistic defaults."
    )
    domain_note = f" The content is from the {domain} domain." if domain else ""
    style_block = f"\n\n{style_context}" if style_context else ""
    user = (
        f"Translate the following text from {source_lang} to {target_lang}.{domain_note}\n\n"
        f"Text:\n{text}"
        f"{style_block}"
    )
    return system, user


# ── Mock backend (no external calls, good for dev/testing) ────────────────────

class MockTranslationBackend(TranslationBackend):
    """
    Deterministic mock that prefixes text with the target language code.
    Useful for local development and testing without API keys.
    """

    MOCK_MAP = {
        ("en", "fr"): ("[FR] {}", 0.92),
        ("en", "de"): ("[DE] {}", 0.91),
        ("en", "es"): ("[ES] {}", 0.93),
        ("en", "ja"): ("[JA] {}", 0.88),
        ("en", "zh"): ("[ZH] {}", 0.87),
        ("en", "pt"): ("[PT] {}", 0.90),
        ("en", "it"): ("[IT] {}", 0.91),
        ("en", "ko"): ("[KO] {}", 0.86),
        ("en", "ar"): ("[AR] {}", 0.84),
        ("en", "nl"): ("[NL] {}", 0.90),
    }

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        src = source_lang.split("-")[0].lower()
        tgt = target_lang.split("-")[0].lower()
        template, confidence = self.MOCK_MAP.get((src, tgt), ("[{}] {}".format(tgt.upper(), "{}"), 0.75))
        return template.format(text), confidence


# ── Anthropic Claude backend ───────────────────────────────────────────────────

class AnthropicTranslationBackend(TranslationBackend):
    """
    Uses Claude to perform translation with provenance-aware prompting.
    Requires ANTHROPIC_API_KEY to be set.
    """

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )

            translated = message.content[0].text.strip()
            # Claude doesn't return a confidence score natively; we use a fixed high value
            confidence = 0.95
            return translated, confidence

        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        except Exception as e:
            raise RuntimeError(f"Anthropic translation failed: {e}")


# ── OpenAI backend ───────────────────────────────────────────────────────────

class OpenAITranslationBackend(TranslationBackend):
    """Requires OPENAI_API_KEY. Same OpenAICompatibleClient LMStudio/vLLM
    reuse below — just pointed at api.openai.com with a real key."""

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the openai provider.")
        client = OpenAICompatibleClient("https://api.openai.com/v1", settings.openai_api_key, settings.openai_model)
        system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)
        try:
            translated = await client.chat(system, user_msg, max_tokens=4096)
        except Exception as e:
            raise RuntimeError(f"OpenAI translation failed: {e}")
        return translated, 0.9  # no native confidence signal, same fixed-value convention as Claude's backend


# ── Google Gemini backend ─────────────────────────────────────────────────────

class GeminiTranslationBackend(TranslationBackend):
    """Requires GEMINI_API_KEY. Distinct from GoogleTranslationBackend
    below (Google Cloud Translation, pure NMT) — this is Gemini the LLM,
    so it can follow style_context the way NMT services can't."""

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for the gemini provider.")
        client = GeminiClient(settings.gemini_api_key, settings.gemini_model)
        system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)
        try:
            translated = await client.chat(system, user_msg, max_tokens=4096)
        except Exception as e:
            raise RuntimeError(f"Gemini translation failed: {e}")
        return translated, 0.9


# ── DeepL backend ─────────────────────────────────────────────────────────────

class DeepLTranslationBackend(TranslationBackend):
    """
    Uses DeepL API for translation.
    Requires DEEPL_API_KEY to be set.
    """

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        try:
            import deepl
            translator = deepl.Translator(settings.deepl_api_key)

            # DeepL uses uppercase lang codes like EN-US, FR
            result = translator.translate_text(
                text,
                source_lang=source_lang.split("-")[0].upper(),
                target_lang=target_lang.upper(),
            )
            return result.text, 0.94

        except ImportError:
            raise RuntimeError("deepl package not installed. Run: pip install deepl")
        except Exception as e:
            raise RuntimeError(f"DeepL translation failed: {e}")


# ── Google Cloud Translation backend ─────────────────────────────────────────

class GoogleTranslationBackend(TranslationBackend):
    """
    Uses Google Cloud Translation API.
    Requires GOOGLE_APPLICATION_CREDENTIALS to be set.
    """

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        try:
            from google.cloud import translate_v2 as gtranslate
            client = gtranslate.Client()

            result = client.translate(
                text,
                source_language=source_lang.split("-")[0],
                target_language=target_lang.split("-")[0],
            )
            return result["translatedText"], 0.90

        except ImportError:
            raise RuntimeError(
                "google-cloud-translate not installed. "
                "Run: pip install google-cloud-translate"
            )
        except Exception as e:
            raise RuntimeError(f"Google translation failed: {e}")


# ── Microsoft Translator backend ──────────────────────────────────────────────

class MSTranslatorTranslationBackend(TranslationBackend):
    """Azure Cognitive Services Translator — requires MS_TRANSLATOR_KEY.
    Pure NMT like DeepL/Google Translate above — style_context is accepted
    for interface compatibility but has nowhere to go (no instruction
    channel), same as those two."""

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        if not settings.ms_translator_key:
            raise RuntimeError("MS_TRANSLATOR_KEY is required for the mstranslator provider.")
        client = MSTranslatorClient(settings.ms_translator_key, settings.ms_translator_region or None, settings.ms_translator_endpoint)
        try:
            translated = await client.translate(text, source_lang, target_lang)
        except Exception as e:
            raise RuntimeError(f"MS Translator translation failed: {e}")
        return translated, 0.90


# ── Ollama backend (local — also usable for Tower/Tower+, see docs) ─────────

class OllamaTranslationBackend(TranslationBackend):
    """Local Ollama server — already used for evaluation (see
    app/core/scoring/ollama_scorer.py) but never for translation until
    Phase 16. Defaults to the same Tower checkpoint peripateticware
    validated for evaluation — Tower models are multi-task (translate AND
    evaluate in one model), see docs/quality-evaluation-research.md §10.
    `model` is overridable per-instance so any locally-pulled model
    (Tower+, Llama, Mistral, ...) is usable, not just the default."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.ollama_translation_model

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        # /api/chat, not /api/generate with a hand-rolled prompt string —
        # see app/core/scoring/ollama_scorer.py's module docstring for why
        # (Ollama applies whichever chat template is embedded in the GGUF
        # itself; Tower+'s different sizes don't share one template to
        # hand-roll correctly, per docs/quality-evaluation-research.md §10).
        import httpx
        system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_msg},
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                translated = resp.json().get("message", {}).get("content", "").strip()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama translation failed ({self.model}): {e}")
        return translated, 0.85  # local/open model, no calibrated confidence signal


# ── LMStudio backend (local OpenAI-compatible server) ────────────────────────

class LMStudioTranslationBackend(TranslationBackend):
    """LMStudio's local server speaks the OpenAI /v1/chat/completions API
    — no real API key needed, `model` is whatever's currently loaded in
    LMStudio (or its model identifier if multiple are available)."""

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        client = OpenAICompatibleClient(settings.lmstudio_url, "lm-studio", settings.lmstudio_model)
        system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)
        try:
            translated = await client.chat(system, user_msg, max_tokens=4096)
        except Exception as e:
            raise RuntimeError(f"LMStudio translation failed — is it running at {settings.lmstudio_url}? ({e})")
        return translated, 0.85


# ── vLLM backend (local OpenAI-compatible server) ─────────────────────────────

class VLLMTranslationBackend(TranslationBackend):
    """vLLM's `--api-server` mode also speaks the OpenAI-compatible API —
    same client as LMStudio, different default port/model."""

    async def translate(self, text, source_lang, target_lang, domain=None, style_context=None):
        client = OpenAICompatibleClient(settings.vllm_url, "EMPTY", settings.vllm_model)
        system, user_msg = _chat_translate_prompt(text, source_lang, target_lang, domain, style_context)
        try:
            translated = await client.chat(system, user_msg, max_tokens=4096)
        except Exception as e:
            raise RuntimeError(f"vLLM translation failed — is it running at {settings.vllm_url}? ({e})")
        return translated, 0.85


# ── Factory ────────────────────────────────────────────────────────────────────

_PROVIDER_CLASSES = {
    "mock": MockTranslationBackend,
    "anthropic": AnthropicTranslationBackend,
    "openai": OpenAITranslationBackend,
    "gemini": GeminiTranslationBackend,
    "deepl": DeepLTranslationBackend,
    "google": GoogleTranslationBackend,
    "mstranslator": MSTranslatorTranslationBackend,
    "ollama": OllamaTranslationBackend,
    "lmstudio": LMStudioTranslationBackend,
    "vllm": VLLMTranslationBackend,
}

_backend_instance: Optional[TranslationBackend] = None


def get_translation_backend(provider: Optional[str] = None) -> TranslationBackend:
    """Returns the configured translation backend. `provider` overrides
    settings.translation_provider (Phase 16 — a specific translate/redrive
    request choosing a different provider than the app default) — passing
    one always builds a fresh instance rather than reusing the cached
    default, mirroring app/core/scoring/factory.py's get_scorer() exactly."""
    global _backend_instance

    requested = (provider or settings.translation_provider).lower()
    if provider is None and _backend_instance is not None:
        return _backend_instance

    cls = _PROVIDER_CLASSES.get(requested)
    if cls is None:
        raise RuntimeError(
            f"Unknown translation provider '{requested}' — expected one of {sorted(_PROVIDER_CLASSES)}"
        )
    if requested == "anthropic" and not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for the anthropic provider.")
    if requested == "deepl" and not settings.deepl_api_key:
        raise RuntimeError("DEEPL_API_KEY is required for the deepl provider.")

    backend = cls()
    if provider is None:
        _backend_instance = backend
        print(f"✓ Translation backend: {backend.__class__.__name__}")
    return backend
