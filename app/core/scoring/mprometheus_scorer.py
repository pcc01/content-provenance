"""
M-Prometheus-as-judge (Unbabel) — a scalar 1-5 MT-quality judge, run locally
through Ollama (GGUF). Unlike the other model scorers here it does NOT use the
shared MQM-JSON contract; see app/core/scoring/mprometheus_prompt.py.

Reference handling (MPROMETHEUS_REFERENCE_MODE, overridable per call):
  auto             - attach a near-exact TranslationExemplar (imported TM) as
                     the "Score 5" reference when retrieval finds one; else
                     reference-free. Glossary terms/rules are always folded
                     into the rubric when retrieval returns them.
  reference_free   - never attach a reference (green-field locale / untrusted TM).
  prefer_reference - like auto, but ScoreResult.needs_review when no reference
                     was found, so a reviewer knows the grade is less anchored.

Transport + resilience mirror ollama_scorer.py: one retry with a longer
timeout, then needs_review instead of raising, so a single slow local
generation can't crash a batch scoring run.
"""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple

import httpx

from app.core.config import settings
from app.core.scoring.base import QualityScorer, ScoreResult
from app.core.scoring.mprometheus_prompt import build_prompt, parse_mprometheus_response
from app.models.schemas import TranslationUnit

VALID_REFERENCE_MODES = {"auto", "reference_free", "prefer_reference"}

# retrieve_style_context() renders exemplars as '"source" -> "target"' facts
# (app/core/graph/retrieval.py::_exemplar_to_fact) — parse that back out to
# recover the raw target as a candidate reference.
_EXEMPLAR_RE = re.compile(r'^"(?P<src>.*)"\s*->\s*"(?P<tgt>.*)"$', re.DOTALL)
# Source-similarity ratio above which a retrieved TM pair is trustworthy
# enough to hand the judge as its gold "Score 5" answer.
_REFERENCE_MATCH_CUTOFF = 0.93


def _lang_name(code: str) -> str:
    try:
        from babel import Locale

        return Locale.parse(code, sep="-").get_display_name("en") or code.upper()
    except Exception:
        return code.upper()


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


async def _resolve_reference_and_glossary(
    unit: TranslationUnit, mode: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort retrieval context — never raises. Returns
    (reference_text | None, glossary_block | None)."""
    if mode == "reference_free":
        return None, None
    try:
        from app.core.graph.retrieval import retrieve_style_context

        ctx = await retrieve_style_context(
            unit.source_text, unit.source_language, unit.target_language, top_k=5,
        )
    except Exception:
        return None, None

    reference = None
    norm_src = _norm(unit.source_text)
    for fact in ctx.exemplars:
        m = _EXEMPLAR_RE.match(fact.text.strip())
        if not m:
            continue
        if SequenceMatcher(None, norm_src, _norm(m.group("src"))).ratio() >= _REFERENCE_MATCH_CUTOFF:
            reference = m.group("tgt").strip()
            break

    glossary_facts = [f.text for f in (list(ctx.terms) + list(ctx.rules))][:12]
    glossary_block = "\n".join(f"- {line}" for line in glossary_facts) or None
    return reference, glossary_block


class MPrometheusQualityScorer(QualityScorer):
    def __init__(self, model: Optional[str] = None, reference_mode: Optional[str] = None):
        self.model = model or settings.mprometheus_model
        self.ollama_url = settings.ollama_url
        mode = (reference_mode or settings.mprometheus_reference_mode or "auto").lower()
        self.reference_mode = mode if mode in VALID_REFERENCE_MODES else "auto"

    async def _generate(self, prompt: str, timeout: float) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()

    async def score(self, unit: TranslationUnit) -> ScoreResult:
        reference, glossary = await _resolve_reference_and_glossary(unit, self.reference_mode)
        prompt = build_prompt(
            source_text=unit.source_text,
            source_language=_lang_name(unit.source_language),
            target_language=_lang_name(unit.target_language),
            hypothesis=unit.target_text or "",
            reference=reference,
            glossary=glossary,
        )
        try:
            raw = await self._generate(prompt, timeout=180.0)
        except httpx.TimeoutException:
            try:
                raw = await self._generate(prompt, timeout=400.0)
            except httpx.HTTPError as e:
                return ScoreResult(
                    score=None, reasons=["evaluator_error"], raw_response=str(e), needs_review=True,
                )
        except httpx.HTTPError as e:
            return ScoreResult(
                score=None, reasons=["evaluator_error"], raw_response=str(e), needs_review=True,
            )

        return parse_mprometheus_response(
            raw, reference_used=reference is not None, reference_mode=self.reference_mode,
        )
