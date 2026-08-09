"""Phase 18 — live model discovery, for every provider that actually offers
more than one selectable model: the three local multi-model servers
(Ollama/LMStudio/vLLM) AND the three hosted LLM vendors (Claude/OpenAI/
Gemini each ship multiple model generations/sizes too — this isn't just a
local-server thing). "You'll need to set up reads of which models are on
the system" — this is that read; for the hosted vendors it's "which models
does this API key actually have access to" rather than "on disk," but the
same not-hardcoded principle applies.

GET /api/v1/models/{provider} - models currently available for that provider

DeepL/Google Translate/MS Translator are deliberately excluded — pure NMT
services with exactly one endpoint each, nothing to pick between.
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.llm_clients import (
    list_anthropic_models, list_gemini_models, list_ollama_models,
    list_openai_compatible_models, list_openai_models,
)

router = APIRouter()

# Translation-side and evaluation-side provider vocabularies disagree on
# what to call the same vendor ("anthropic" vs. "claude" — see api/client.ts's
# TRANSLATE_PROVIDERS/EVALUATE_PROVIDERS docstring on the frontend side for
# why) — both are accepted here so one model picker serves both flows
# without the caller needing to know which vocabulary it's in.
_ALIASES = {"claude": "anthropic"}


class ModelListResponse(BaseModel):
    provider: str
    models: List[str]


@router.get("/{provider}", response_model=ModelListResponse)
async def list_models(provider: str):
    requested = _ALIASES.get(provider.lower(), provider.lower())
    try:
        if requested == "ollama":
            models = await list_ollama_models(settings.ollama_url)
        elif requested == "lmstudio":
            models = await list_openai_compatible_models(settings.lmstudio_url)
        elif requested == "vllm":
            models = await list_openai_compatible_models(settings.vllm_url)
        elif requested == "openai":
            if not settings.openai_api_key:
                raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not set.")
            models = await list_openai_models(settings.openai_api_key)
        elif requested == "gemini":
            if not settings.gemini_api_key:
                raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not set.")
            models = await list_gemini_models(settings.gemini_api_key)
        elif requested == "anthropic":
            if not settings.anthropic_api_key:
                raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is not set.")
            models = await list_anthropic_models(settings.anthropic_api_key)
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{provider}' has no model list to discover — it's either a single-model NMT "
                    "service (deepl/google/mstranslator) or not a recognized provider."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Couldn't reach {requested} to list its models: {e}",
        )
    return ModelListResponse(provider=provider.lower(), models=models)
