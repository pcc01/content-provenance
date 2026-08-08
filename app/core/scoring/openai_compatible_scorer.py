"""Shared scorer for any provider speaking the OpenAI /v1/chat/completions
API — OpenAI itself, LMStudio, vLLM (Phase 16). Each just supplies a
differently-configured OpenAICompatibleClient (see app/core/llm_clients.py);
all three use the exact same MQM prompt/parsing contract as
ClaudeQualityScorer (app/core/scoring/mqm_prompt.py), so scores are
comparable across providers instead of each having its own rubric.
"""

from app.core.llm_clients import OpenAICompatibleClient
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.mqm_prompt import SYSTEM_PROMPT, build_user_message, parse_mqm_response
from app.models.schemas import TranslationUnit


class OpenAICompatibleScorer(QualityScorer):
    def __init__(self, client: OpenAICompatibleClient, provider_label: str):
        self.client = client
        self.provider_label = provider_label

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        user_msg = build_user_message(
            unit.source_text, unit.source_language, unit.target_text or "", unit.target_language,
        )
        try:
            raw = await self.client.chat(SYSTEM_PROMPT, user_msg)
        except Exception as e:
            return ScoreResult(
                score=None, reasons=["evaluator_error"], raw_response=f"{self.provider_label}: {e}",
                needs_review=True,
            )
        return parse_mqm_response(raw)
