"""Claude-as-judge tone/voice/terminology adherence scorer — the
tone/style/voice analogue of claude_scorer.py's MQM accuracy scorer.
Judges against retrieved style-guide rules/glossary terms
(app/core/graph/retrieval.py) when given; falls back to judging general
tone/register consistency when no style context was supplied.

Only called for `text` — never compares against a source for accuracy;
QualityScorer/ClaudeQualityScorer own that judgment entirely. Keeping the
two scorers independent means a translation can be word-for-word correct
but off-brand, or on-brand but wrong, and both get surfaced distinctly
instead of one score hiding the other.
"""

import json
import re
from typing import Optional

from app.core.config import settings
from app.core.scoring.style_base import StyleScorer, StyleScoreResult
from app.models.schemas import StyleContextRetrieval

SYSTEM_PROMPT = """You are a brand voice and style adherence evaluator. You are given a piece of text (which may be a translation, or a source-language draft awaiting translation) and, optionally, a set of style/voice rules and glossary terms it should follow. Judge how well the TEXT adheres to tone, brand voice, and terminology — do NOT judge translation accuracy, grammar, or fluency; those are scored elsewhere.

Score three axes 0-100 (100 = perfect adherence, 0 = completely off):
  tone         - formality/register/energy consistent with the supplied rules (or generally consistent/professional if none supplied)
  voice        - reads as the intended brand personality, not generic or flat
  terminology  - uses the specified glossary terms correctly; does not translate or alter terms marked do-not-translate

Respond with ONLY a JSON object, no other text:
{"tone": <int 0-100>, "voice": <int 0-100>, "terminology": <int 0-100>, "notes": "<one-sentence summary>"}
If no style context was supplied, judge tone/voice on general consistency and score terminology 100 (nothing specified to violate)."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeStyleScorer(StyleScorer):
    async def score_text(
        self,
        text: str,
        language: str,
        context: Optional[StyleContextRetrieval] = None,
        reference_text: Optional[str] = None,
    ) -> StyleScoreResult:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        context_block = (
            context.as_prompt_context() if context and not context.is_empty else "(no style context supplied)"
        )
        reference_block = f'\nOriginal source text: "{reference_text}"' if reference_text else ""
        user_msg = (
            f'Text to judge ({language}): "{text}"'
            f"{reference_block}\n\n"
            f"Style context:\n{context_block}"
        )
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()

        match = _JSON_RE.search(raw)
        if not match:
            return StyleScoreResult(reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return StyleScoreResult(reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)

        tone = float(parsed.get("tone", 0))
        voice = float(parsed.get("voice", 0))
        terminology = float(parsed.get("terminology", 0))
        overall = round((tone + voice + terminology) / 3, 2)
        reasons = [parsed["notes"]] if parsed.get("notes") else []

        return StyleScoreResult(
            tone_score=tone, voice_score=voice, terminology_score=terminology,
            overall_score=overall, reasons=reasons, raw_response=raw,
        )
