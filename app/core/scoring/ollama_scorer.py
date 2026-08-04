"""
Local Ollama QE scorer — mirrors peripateticware's TowerInstruct-via-Ollama
approach (frontend/scripts/qa_review_llamacpp.py / localization_qa_crawler.py):
ask a local model to list translation errors; "NO ERRORS FOUND" -> clean.

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


def _build_prompt(source: str, target: str, lang_name: str) -> str:
    return (
        f"[INST] Identify all translation errors and grammatical mistakes in the "
        f"following target text, which was translated from English to {lang_name}.\n"
        f'Source: "{source}"\n'
        f'Target: "{target}"\n'
        f"Output format: List the error, location, and severity. If there are no "
        f"errors, respond with exactly: NO ERRORS FOUND. [/INST]"
    )


async def preflight_check(ollama_url: str, model: str, timeout: int = 120) -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": "[INST] Say OK. [/INST]", "stream": False},
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

    async def _generate(self, prompt: str, timeout: int = 180) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        lang_name = _lang_name(unit.target_language)
        prompt = _build_prompt(unit.source_text, unit.target_text or "", lang_name)
        try:
            verdict = await self._generate(prompt)
        except httpx.TimeoutException:
            try:
                verdict = await self._generate(prompt, timeout=400)
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
