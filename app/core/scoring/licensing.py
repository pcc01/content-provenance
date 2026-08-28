"""
Which evaluation signals are safe to lean on in a commercial deliverable,
and which are research/non-commercial only.

Decision 4 of the report-gated redrive plan: this system runs as an internal
service, not a shipped product, but a produced Quality Report separates the
two lanes so a downstream deliverable that must be commercially clean knows
which scores it may cite.

Lane assignment:
  - deterministic.py's free checks: no model, no license concern -> safe.
  - Hosted LLM judges (Claude / OpenAI / Gemini): commercial use is covered
    by the vendor's API terms -> safe.
  - Local open-weight judges via lmstudio/vllm/ollama (Tower+): depends on
    the specific checkpoint the operator loads, so treated as UNKNOWN here
    (the operator asserts it via SCORER_COMMERCIAL_OVERRIDES) rather than
    this module guessing from a provider name.
  - M-Prometheus: Qwen Research License Agreement (it is a Qwen2.5-Instruct
    finetune, and Unbabel ships it under Qwen's research terms, which
    propagate downstream) -> research / non-commercial only.
  - XCOMET / CometKiwi checkpoints: CC-BY-NC-SA-4.0 -> non-commercial only.
"""

import json
import os
from typing import Dict, Optional

# scorer name (as recorded on QualityScore.scorer / QualityReport.scoring_provider)
# -> (commercial_safe | None for "operator must assert", license id, short note)
_LANES: Dict[str, tuple] = {
    "deterministic": (True, "n/a", "Rule-based checks, no model involved."),
    "claude": (True, "commercial-api", "Anthropic API — commercial use per Anthropic's terms."),
    "openai": (True, "commercial-api", "OpenAI API — commercial use per OpenAI's terms."),
    "gemini": (True, "commercial-api", "Google Generative Language API — commercial use per Google's terms."),
    "mprometheus": (
        False, "qwen-research",
        "Qwen Research License Agreement (Qwen2.5 finetune) — research / non-commercial only, "
        "restrictions propagate downstream.",
    ),
    "xcomet": (False, "cc-by-nc-sa-4.0", "CC-BY-NC-SA-4.0 — non-commercial only."),
    "comet_kiwi": (False, "cc-by-nc-sa-4.0", "CC-BY-NC-SA-4.0 — non-commercial only."),
    # Local generic servers — the loaded checkpoint decides; operator asserts.
    "ollama": (None, "depends-on-checkpoint", "Depends on the GGUF the operator has loaded."),
    "lmstudio": (None, "depends-on-checkpoint", "Depends on the model the operator has loaded."),
    "vllm": (None, "depends-on-checkpoint", "Depends on the model the operator has loaded."),
}


def _overrides() -> Dict[str, bool]:
    """SCORER_COMMERCIAL_OVERRIDES, JSON, e.g. {"ollama": true} when the
    operator has confirmed the local checkpoint they run is commercially
    licensed (or false to force the other way)."""
    raw = os.getenv("SCORER_COMMERCIAL_OVERRIDES")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return {str(k).lower(): bool(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, AttributeError):
        return {}


def commercial_safe(scorer: Optional[str]) -> Optional[bool]:
    """True (safe), False (non-commercial), or None (operator must assert —
    unknown local checkpoint, or an unrecognized scorer name)."""
    if not scorer:
        return None
    key = scorer.lower()
    ov = _overrides()
    if key in ov:
        return ov[key]
    entry = _LANES.get(key)
    return entry[0] if entry else None


def license_note(scorer: Optional[str]) -> str:
    entry = _LANES.get((scorer or "").lower())
    return entry[2] if entry else "License not classified — treat as non-commercial until confirmed."


def license_id(scorer: Optional[str]) -> str:
    entry = _LANES.get((scorer or "").lower())
    return entry[1] if entry else "unclassified"
