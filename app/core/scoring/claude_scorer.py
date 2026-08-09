"""
Claude-as-judge quality scorer — MQM-style (Multidimensional Quality Metrics)
error annotation, using the shared prompt/parsing contract in mqm_prompt.py
(Phase 16 — every chat-completion provider shares this exact rubric now,
not a per-provider near-duplicate).

Only called for pairs app/core/scoring/deterministic.py's free checks didn't
already resolve (see factory.py's CompositeScorer).
"""

from typing import Optional

from app.core.config import settings
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.mqm_prompt import SYSTEM_PROMPT, build_user_message, parse_mqm_response
from app.models.schemas import TranslationUnit


class ClaudeQualityScorer(QualityScorer):
    # Phase 18 — model overridable per-instance (GET /api/v1/models/claude
    # lists Anthropic's own Models API); None still falls back to this
    # default rather than erroring, since get_scorer() always passes
    # `model=` explicitly (None when the caller didn't ask for one).
    def __init__(self, model: Optional[str] = None):
        self.model = model or "claude-sonnet-4-20250514"

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        user_msg = build_user_message(unit.source_text, unit.source_language, unit.target_text or "", unit.target_language)
        message = client.messages.create(
            model=self.model,
            max_tokens=768,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()
        return parse_mqm_response(raw)
