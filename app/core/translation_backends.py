"""
Translation Backend Abstraction Layer
Supports mock, Anthropic Claude, DeepL, and Google Translate.

Switch providers via the TRANSLATION_PROVIDER environment variable.
"""

from typing import Tuple
from app.core.config import settings


# ── Base interface ─────────────────────────────────────────────────────────────

class TranslationBackend:
    """Abstract translation backend. Implement translate() for each provider."""

    async def translate(
        self, text: str, source_lang: str, target_lang: str, domain: str = None
    ) -> Tuple[str, float]:
        """
        Returns (translated_text, confidence_score 0.0–1.0).
        """
        raise NotImplementedError


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

    async def translate(self, text, source_lang, target_lang, domain=None):
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

    SYSTEM_PROMPT = """You are a professional translator. Translate the provided text accurately and naturally.
Preserve formatting, tone, and meaning. Do not add explanations or commentary — return only the translation."""

    async def translate(self, text, source_lang, target_lang, domain=None):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            domain_note = f" The content is from the {domain} domain." if domain else ""
            user_msg = (
                f"Translate the following text from {source_lang} to {target_lang}.{domain_note}\n\n"
                f"Text:\n{text}"
            )

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
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


# ── DeepL backend ─────────────────────────────────────────────────────────────

class DeepLTranslationBackend(TranslationBackend):
    """
    Uses DeepL API for translation.
    Requires DEEPL_API_KEY to be set.
    """

    async def translate(self, text, source_lang, target_lang, domain=None):
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

    async def translate(self, text, source_lang, target_lang, domain=None):
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


# ── Factory ────────────────────────────────────────────────────────────────────

_backend_instance: TranslationBackend = None


def get_translation_backend() -> TranslationBackend:
    """
    Return the configured translation backend singleton.
    Controlled by TRANSLATION_PROVIDER env var.
    """
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    provider = settings.translation_provider.lower()

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the anthropic provider.")
        _backend_instance = AnthropicTranslationBackend()

    elif provider == "deepl":
        if not settings.deepl_api_key:
            raise RuntimeError("DEEPL_API_KEY is required for the deepl provider.")
        _backend_instance = DeepLTranslationBackend()

    elif provider == "google":
        _backend_instance = GoogleTranslationBackend()

    else:
        # Default: mock
        _backend_instance = MockTranslationBackend()

    print(f"✓ Translation backend: {_backend_instance.__class__.__name__}")
    return _backend_instance
