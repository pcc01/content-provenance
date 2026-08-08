"""
Local Ollama QE scorer — mirrors peripateticware's TowerInstruct-via-Ollama
approach (frontend/scripts/qa_review_llamacpp.py / localization_qa_crawler.py):
ask a local model to list translation errors; "NO ERRORS FOUND" -> clean.

Uses Ollama's /api/chat endpoint (Phase 16), not /api/generate with a
hand-rolled prompt string — this project's original /api/generate call
wrapped its instruction in Mistral/Llama-2-chat-style `[INST]...[/INST]`
tags, but TowerInstruct is documented to expect ChatML, and Tower+ (the
current default, see app/core/config.py's ollama_qe_model) spans two
different base-model families (Gemma 2, Qwen 2.5) with no shared chat
template at all — see docs/quality-evaluation-research.md §10 for how this
mismatch was found. /api/chat sidesteps the whole problem: Ollama applies
whichever template is embedded in the GGUF itself, so this file no longer
needs to know or guess which one that is.

Resilience pattern ported from that crawler: a local model can stall on a
single generation (cold-loading weights, GC pause, brief contention) even
after a successful preflight check elsewhere, so one slow/failed call
shouldn't crash a whole batch scoring run — this retries once with a longer
timeout, then reports needs_review instead of raising.
"""

from typing import Optional

import httpx

from app.core.config import settings
from app.core.scoring.base import QualityScorer, ScoreResult
from app.models.schemas import TranslationUnit


def _lang_name(code: str) -> str:
    try:
        from babel import Locale
        name = Locale.parse(code, sep="-").get_display_name("en")
        if name:
            return name
    except Exception:
        pass
    return code.upper()


def _build_user_message(source: str, target: str, lang_name: str) -> str:
    return (
        f"Identify all translation errors and grammatical mistakes in the "
        f"following target text, which was translated from English to {lang_name}.\n"
        f'Source: "{source}"\n'
        f'Target: "{target}"\n'
        f"Output format: List the error, location, and severity. If there are no "
        f"errors, respond with exactly: NO ERRORS FOUND."
    )


async def preflight_check(ollama_url: str, model: str, timeout: int = 120) -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={"model": model, "messages": [{"role": "user", "content": "Say OK."}], "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            return False


class OllamaQualityScorer(QualityScorer):
    def __init__(self, ollama_url: Optional[str] = None, model: Optional[str] = None):
        self.ollama_url = ollama_url or settings.ollama_url
        self.model = model or settings.ollama_qe_model

    async def _chat(self, user_message: str, timeout: int = 180) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": user_message}],
                    "stream": False,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        lang_name = _lang_name(unit.target_language)
        user_message = _build_user_message(unit.source_text, unit.target_text or "", lang_name)
        try:
            verdict = await self._chat(user_message)
        except httpx.TimeoutException:
            try:
                verdict = await self._chat(user_message, timeout=400)
            except httpx.HTTPError as e:
                return ScoreResult(score=None, reasons=["evaluator_error"], raw_response=str(e), needs_review=True)
        except httpx.HTTPError as e:
            return ScoreResult(score=None, reasons=["evaluator_error"], raw_response=str(e), needs_review=True)

        if "no errors found" in verdict.lower():
            return ScoreResult(score=100, raw_response=verdict)

        # TowerInstruct's free-text error listing doesn't reliably carry
        # per-error severity the way the Claude scorer's MQM-JSON prompt
        # does, so — like the peripateticware crawler this is ported from —
        # this treats "flagged at all" as pass/fail rather than trying to
        # parse severities out of prose. The score sits below the common 80
        # default threshold so flagged pairs get picked up for redrive
        # without claiming a confidence the free-text output doesn't support.
        return ScoreResult(score=40, reasons=["evaluator_flagged"], raw_response=verdict)
