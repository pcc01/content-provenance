"""Shared MQM-style prompt + response parsing — extracted out of
claude_scorer.py (Phase 16) so every chat-completion-capable provider
(Claude, OpenAI, Gemini, Ollama/Tower, LMStudio, vLLM) scores against the
exact same rubric and JSON contract instead of five near-duplicate prompts
drifting apart over time. Provider-specific scorer classes only need to
know how to get a raw text completion back from their API — this module
owns "what to ask" and "how to turn the answer into a ScoreResult."

See app/core/scoring/mqm_types.py for the 44-item MQM-Core taxonomy this
prompt is built from, and docs/quality-evaluation-research.md §2.4 for why
the severity weights (25/10/3) are this codebase's own choice, not MQM's
literal 25/5/1 defaults.
"""

import json
import re

from app.core.scoring.base import ScoreResult
from app.core.scoring.mqm_types import build_prompt_rubric
from app.models.schemas import ScoreError, ScoreErrorSeverity

SYSTEM_PROMPT = f"""You are a professional translation quality evaluator using MQM (Multidimensional Quality Metrics) error annotation. Given a source text and its translation, identify every translation error. For each distinct error, report:
  error_type - the closest matching MQM error type mnemonic from this list, grouped by dimension:
{build_prompt_rubric()}
  severity - one of:
    critical - meaning is wrong, reversed, or the translation would mislead a reader
    major    - a clear grammar/terminology/fluency error a native reader would notice
    minor    - a small stylistic or cosmetic issue
    neutral  - a different solution would be preferable, but the translator should not be penalized for it

Respond with ONLY a JSON object, no other text:
{{"errors": [{{"error_type": "<mnemonic>", "severity": "<critical|major|minor|neutral>", "count": <int>}}, ...], "notes": "<one-sentence summary>"}}
If there are no errors at all, respond with {{"errors": [], "notes": "no errors found"}}."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_SEVERITY_WEIGHT = {
    ScoreErrorSeverity.CRITICAL: 25,
    ScoreErrorSeverity.MAJOR: 10,
    ScoreErrorSeverity.MINOR: 3,
    ScoreErrorSeverity.NEUTRAL: 0,
}


def build_user_message(source_text: str, source_language: str, target_text: str, target_language: str) -> str:
    return (
        f'Source ({source_language}): "{source_text}"\n'
        f'Translation ({target_language}): "{target_text}"'
    )


def parse_mqm_response(raw: str) -> ScoreResult:
    """Turns a model's raw text completion into a ScoreResult — shared by
    every provider using SYSTEM_PROMPT's JSON contract. `raw` is the
    provider's completion text; if it isn't parseable JSON matching the
    contract, this returns needs_review=True rather than guessing, the
    same fallback claude_scorer.py always used."""
    match = _JSON_RE.search(raw)
    if not match:
        return ScoreResult(score=None, reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return ScoreResult(score=None, reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True)

    errors = []
    penalty = 0
    hard_fail = False
    for item in parsed.get("errors", []):
        try:
            severity = ScoreErrorSeverity(str(item.get("severity", "")).lower())
        except ValueError:
            continue  # unrecognized severity from the model — skip rather than guess
        count = max(1, int(item.get("count", 1)))
        errors.append(ScoreError(severity=severity, count=count, error_type=item.get("error_type") or None))
        penalty += _SEVERITY_WEIGHT[severity] * count
        if severity == ScoreErrorSeverity.CRITICAL:
            hard_fail = True

    score = max(0, 100 - penalty)
    reasons = ["evaluator_flagged"] if errors else []
    return ScoreResult(score=score, reasons=reasons, errors=errors, raw_response=raw, hard_fail=hard_fail)
