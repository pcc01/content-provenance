"""Scorer selection and composition."""

from typing import Optional

from app.core.config import settings
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.deterministic import deterministic_score
from app.models.schemas import QualityScore, TranslationUnit


class CompositeScorer(QualityScorer):
    """Runs deterministic.py's free checks first; only calls the configured
    model-based scorer for pairs those checks don't already resolve."""

    def __init__(self, model_scorer: QualityScorer, scorer_name: str):
        self.model_scorer = model_scorer
        self.scorer_name = scorer_name

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        floor, reasons = deterministic_score(unit.source_text, unit.target_text, unit.target_language)
        if floor is not None:
            return ScoreResult(score=floor, reasons=reasons, deterministic=True)
        return await self.model_scorer.score(unit)


_scorer_instance: Optional[QualityScorer] = None
_scorer_name: Optional[str] = None


def get_scorer(provider: Optional[str] = None, model: Optional[str] = None) -> QualityScorer:
    """provider overrides settings.scoring_provider (e.g. a specific redrive
    run asking for a different scorer than the app default) — passing one
    always builds a fresh instance rather than reusing the cached default.
    `model` (Phase 18) additionally overrides WHICH model runs within
    provider, for ollama/lmstudio/vllm — see GET /api/v1/models/{provider}.
    Ignored (not an error) for every other provider, which has exactly one
    configured model."""
    global _scorer_instance, _scorer_name

    requested = (provider or settings.scoring_provider).lower()
    if provider is None and model is None and _scorer_instance is not None:
        return _scorer_instance

    if requested == "claude":
        from app.core.scoring.claude_scorer import ClaudeQualityScorer
        model_scorer: QualityScorer = ClaudeQualityScorer(model=model)
    elif requested == "ollama":
        from app.core.scoring.ollama_scorer import OllamaQualityScorer
        model_scorer = OllamaQualityScorer(model=model)
    elif requested == "gemini":
        from app.core.scoring.gemini_scorer import GeminiQualityScorer
        model_scorer = GeminiQualityScorer(model=model)
    elif requested in ("openai", "lmstudio", "vllm"):
        # Phase 16 — all three speak the OpenAI-compatible chat API;
        # only the client config differs (app/core/llm_clients.py).
        from app.core.llm_clients import OpenAICompatibleClient
        from app.core.scoring.openai_compatible_scorer import OpenAICompatibleScorer
        if requested == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for the openai provider.")
            client = OpenAICompatibleClient("https://api.openai.com/v1", settings.openai_api_key, model or settings.openai_model)
        elif requested == "lmstudio":
            client = OpenAICompatibleClient(settings.lmstudio_url, "lm-studio", model or settings.lmstudio_model)
        else:  # vllm
            client = OpenAICompatibleClient(settings.vllm_url, "EMPTY", model or settings.vllm_model)
        model_scorer = OpenAICompatibleScorer(client, requested)
    else:
        raise RuntimeError(
            f"Unknown scoring provider '{requested}' — expected one of "
            "'claude', 'ollama', 'openai', 'gemini', 'lmstudio', 'vllm'"
        )

    scorer = CompositeScorer(model_scorer, scorer_name=requested)
    if provider is None and model is None:
        _scorer_instance = scorer
        _scorer_name = requested
    return scorer
