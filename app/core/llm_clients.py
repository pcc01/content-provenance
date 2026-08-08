"""Phase 16 — thin, dependency-light REST clients shared by the new
translation backends and scorers (app/core/translation_backends.py,
app/core/scoring/openai_scorer.py, etc.). Raw httpx, no provider SDKs —
same "no heavy dependency for a simple REST call" choice already made for
app/core/scoring/ollama_scorer.py (which talks to Ollama's /api/generate
directly rather than pulling in an `ollama` package).

  OpenAICompatibleClient — the OpenAI Chat Completions API shape, shared
    by OpenAI itself, LMStudio, and vLLM (both LMStudio and vLLM expose an
    OpenAI-compatible /v1/chat/completions endpoint — one client class,
    three different base_url/api_key configs, not three implementations).
  GeminiClient          — Google's Generative Language API (different
    request/response shape from OpenAI's).
  MSTranslatorClient    — Azure Cognitive Services Translator Text API —
    NMT, not a chat model; translate-only, same category as the existing
    DeepLTranslationBackend/GoogleTranslationBackend, no evaluate capability.
"""

from typing import Optional

import httpx


class OpenAICompatibleClient:
    """Any server speaking the OpenAI /v1/chat/completions contract:
    OpenAI itself, LMStudio (`http://localhost:1234/v1`), vLLM's OpenAI-
    compatible server (`http://localhost:8000/v1`). api_key is required by
    OpenAI's real API; LMStudio/vLLM generally ignore it but the header
    still needs *a* value, hence the "not-needed" placeholders each
    backend passes."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat(self, system: str, user: str, max_tokens: int = 768) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()


class GeminiClient:
    """Google's Generative Language API — https://ai.google.dev/api/generate-content.
    Different shape from OpenAI's: system instruction is a separate field,
    content is a list of {parts: [{text}]}, response nests through
    candidates[0].content.parts[0].text."""

    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat(self, system: str, user: str, max_tokens: int = 768) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                params={"key": self.api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                # Gemini returns 200 with no candidates when content is
                # blocked by safety filters — surface that distinctly
                # rather than a confusing KeyError.
                reason = data.get("promptFeedback", {}).get("blockReason", "no candidates returned")
                raise RuntimeError(f"Gemini returned no output: {reason}")
            return candidates[0]["content"]["parts"][0]["text"].strip()


class MSTranslatorClient:
    """Azure Cognitive Services Translator Text API —
    https://learn.microsoft.com/azure/ai-services/translator/reference/v3-0-translate.
    Traditional NMT, not an LLM — translate() only, no chat/evaluate
    capability, same category as DeepL/Google Translate already in
    app/core/translation_backends.py."""

    def __init__(self, api_key: str, region: Optional[str], endpoint: str = "https://api.cognitive.microsofttranslator.com"):
        self.api_key = api_key
        self.region = region
        self.endpoint = endpoint.rstrip("/")

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.endpoint}/translate",
                params={"api-version": "3.0", "from": source_lang.split("-")[0], "to": target_lang.split("-")[0]},
                headers=headers,
                json=[{"text": text}],
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0]["translations"][0]["text"]
