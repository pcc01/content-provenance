"""
Claude-as-judge quality scorer — MQM-style (Multidimensional Quality Metrics)
error counting: score = max(0, 100 - 25*critical - 10*major - 3*minor).

Only called for pairs app/core/scoring/deterministic.py's free checks didn't
already resolve (see factory.py's CompositeScorer).
"""

import json
import re

from app.core.config import settings
from app.core.scoring.base import QualityScorer, ScoreResult
from app.models.schemas import ScoreError, TranslationUnit

SYSTEM_PROMPT = """You are a professional translation quality evaluator using MQM-style error annotation. Given a source text and its translation, identify every translation error and classify each by severity:
  CRITICAL - meaning is wrong, reversed, or the translation would mislead a reader
  MAJOR - a clear grammar/terminology/fluency error a native reader would notice
  MINOR - a small stylistic or cosmetic issue

Respond with ONLY a JSON object, no other text:
{"critical": <int>, "major": <int>, "minor": <int>, "notes": "<one-sentence summary>"}
If there are no errors at all, respond with {"critical": 0, "major": 0, "minor": 0, "notes": "no errors found"}."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeQualityScorer(QualityScorer):
    async def score(self, unit: TranslationUnit) -> ScoreResult:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        user_msg = (
            f'Source ({unit.source_language}): "{unit.source_text}"\n'
            f'Translation ({unit.target_language}): "{unit.target_text or ""}"'
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
            return ScoreResult(score=None, reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return ScoreResult(score=None, reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)

        critical = int(parsed.get("critical", 0))
        major = int(parsed.get("major", 0))
        minor = int(parsed.get("minor", 0))
        score = max(0, 100 - 25 * critical - 10 * major - 3 * minor)

        errors = [
            ScoreError(severity=sev, count=n)
            for sev, n in (("critical", critical), ("major", major), ("minor", minor))
            if n > 0
        ]
        reasons = ["evaluator_flagged"] if errors else []

        return ScoreResult(score=score, reasons=reasons, errors=errors, raw_response=raw)
