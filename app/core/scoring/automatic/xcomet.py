"""XCOMET (Unbabel) — a learned MT metric that returns BOTH a 0-1 quality
score AND localized error spans tagged minor / major / critical. This is
the signal M-Prometheus (a scalar 1-5 judge) and the MQM-JSON judges
structurally can't give: character offsets into the target text.

Runs reference-free (source + hypothesis only), like COMET-Kiwi — the only
mode that fits this system, where no independent human reference exists at
scoring time for most units.

Licensing: the XCOMET checkpoints are CC-BY-NC-SA-4.0, gated behind a free
Hugging Face login. Same posture as comet_kiwi.py — internal / non-commercial
evaluation only, an explicit decision by the project owner. A report item
whose spans came from XCOMET is marked commercial_safe=false accordingly
(app/core/scoring/licensing.py).

Same "heavy, NOT-installed-by-default, lazy-import, degrade to None" contract
as comet_kiwi.py: `pip install unbabel-comet` pulls torch + transformers +
pytorch-lightning, and the checkpoint needs a one-time authenticated
download. Not exercised by CI — the test suite monkeypatches
score_xcomet_batch to cover the plumbing.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from app.models.schemas import TranslationUnit

# XL (~3.5B, ~15GB GPU) by default; override to Unbabel/XCOMET-XXL (~10.7B)
# on a bigger card, or to a local path.
_CHECKPOINT = os.getenv("XCOMET_CHECKPOINT", "Unbabel/XCOMET-XL")
_model = None
_load_attempted = False


def xcomet_available() -> bool:
    try:
        import comet  # noqa: F401
    except ImportError:
        return False
    return True


def _load_model():
    global _model, _load_attempted
    if _load_attempted:
        return _model
    _load_attempted = True
    try:
        from comet import download_model, load_from_checkpoint

        model_path = download_model(_CHECKPOINT)
        _model = load_from_checkpoint(model_path)
        print(f"✓ XCOMET loaded: {_CHECKPOINT}")
    except Exception as e:  # package missing, license not accepted, no network
        print(f"⚠  XCOMET unavailable ({e}); xcomet scoring will return None.")
        _model = None
    return _model


def _normalize_spans(raw_spans: Any, target_text: str) -> List[Dict[str, Any]]:
    """XCOMET's per-segment `metadata.error_spans` shape varies a little by
    version — normalize to {text, severity, start, end}. `start`/`end` are
    character offsets into target_text when we can recover them, else None."""
    out: List[Dict[str, Any]] = []
    for s in raw_spans or []:
        text = s.get("text") if isinstance(s, dict) else getattr(s, "text", None)
        severity = (s.get("severity") if isinstance(s, dict) else getattr(s, "severity", None)) or "minor"
        start = s.get("start") if isinstance(s, dict) else getattr(s, "start", None)
        end = s.get("end") if isinstance(s, dict) else getattr(s, "end", None)
        if start is None and text:
            idx = target_text.find(text)
            if idx >= 0:
                start, end = idx, idx + len(text)
        out.append({"text": text, "severity": str(severity).lower(), "start": start, "end": end})
    return out


async def score_xcomet_batch(
    units: List[TranslationUnit], gpus: int = 0,
) -> List[Optional[Dict[str, Any]]]:
    """One result per unit: {"score": 0-1 float, "spans": [{text,severity,start,end}]}
    or None where the model is unavailable / the unit has no target_text.
    CPU by default (gpus=0) — this is a batch/offline path, never live."""
    model = _load_model()
    if model is None:
        return [None] * len(units)

    scorable = [(i, u) for i, u in enumerate(units) if u.target_text]
    if not scorable:
        return [None] * len(units)

    data = [{"src": u.source_text, "mt": u.target_text} for _, u in scorable]
    loop = asyncio.get_running_loop()

    def _predict():
        return model.predict(data, batch_size=8, gpus=gpus)

    output = await loop.run_in_executor(None, _predict)

    metadata = getattr(output, "metadata", None)
    error_spans = getattr(metadata, "error_spans", None) if metadata is not None else None

    results: Dict[int, Dict[str, Any]] = {}
    for local_idx, (orig_idx, unit) in enumerate(scorable):
        spans = error_spans[local_idx] if error_spans and local_idx < len(error_spans) else []
        results[orig_idx] = {
            "score": output.scores[local_idx],
            "spans": _normalize_spans(spans, unit.target_text or ""),
        }
    return [results.get(i) for i in range(len(units))]
