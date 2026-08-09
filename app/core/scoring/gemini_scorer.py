"""Google Gemini quality scorer (Phase 16) — same MQM prompt/parsing
contract as every other chat-completion-capable scorer (mqm_prompt.py).
Requires GEMINI_API_KEY.
"""

from typing import Optional

from app.core.config import settings
from app.core.llm_clients import GeminiClient
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.mqm_prompt import SYSTEM_PROMPT, build_user_message, parse_mqm_response
from app.models.schemas import TranslationUnit


class GeminiQualityScorer(QualityScorer):
    # Phase 18 — model overridable per-instance, GET /api/v1/models/gemini
    # lists what Google's API currently serves.
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.gemini_model

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for the gemini provider.")
        client = GeminiClient(settings.gemini_api_key, self.model)
        user_msg = build_user_message(
            unit.source_text, unit.source_language, unit.target_text or "", unit.target_language,
        )
        try:
            raw = await client.chat(SYSTEM_PROMPT, user_msg)
        except Exception as e:
            return ScoreResult(score=None, reasons=["evaluator_error"], raw_response=str(e), needs_review=True)
        return parse_mqm_response(raw)
