"""COMET-Kiwi (reference-free MT quality estimation) — Unbabel/IST's
neural, trained metric (github.com/Unbabel/COMET). Reference-free means
only source + hypothesis are needed, unlike METEOR or reference-based
COMET — the only COMET variant that fits this system's shape, since no
independent human reference exists at scoring time for most units. See
docs/quality-evaluation-research.md §3 for the full evaluation.

Licensing (§3.1/§8.1 of that doc): the wmt22-cometkiwi-da checkpoint is
CC-BY-NC-SA-4.0 and gated behind a free Hugging Face login + one-click
license acceptance — no fee. This project has scoped its use to internal/
non-commercial evaluation as an explicit decision by the project owner
(open-source, not commercialized). If that changes, this module and the
license acceptance on the HF model page both need revisiting.

Deliberately a heavy, NOT-installed-by-default dependency (see
requirements.txt) — `pip install unbabel-comet` pulls in torch +
transformers + pytorch-lightning (multiple GB), and the checkpoint itself
needs a one-time authenticated download. Every entry point here lazy-
imports so environments without it installed don't break at import time —
the same pattern already used for anthropic (claude_scorer.py) and
sentence-transformers (app/core/graph/embeddings.py). Not exercised by
this system's test suite for the same reason ClaudeQualityScorer's actual
API call isn't (see tests/test_automatic_metrics.py): no heavyweight
model download is assumed present in CI/dev by default.
"""

import asyncio
from typing import List, Optional

from app.models.schemas import TranslationUnit

_CHECKPOINT = "Unbabel/wmt22-cometkiwi-da"
_model = None
_load_attempted = False


def comet_kiwi_available() -> bool:
    try:
        import comet  # noqa: F401
    except ImportError:
        return False
    return True


def _load_model():
    """Downloads (first call only — requires a Hugging Face login and
    accepting this gated checkpoint's license) and caches the COMET-Kiwi
    model. Returns None on any failure (package missing, license not
    accepted, no network) — callers must treat None as "unavailable,"
    never let a load failure raise past a scoring call."""
    global _model, _load_attempted
    if _load_attempted:
        return _model
    _load_attempted = True
    try:
        from comet import download_model, load_from_checkpoint
        model_path = download_model(_CHECKPOINT)
        _model = load_from_checkpoint(model_path)
        print(f"✓ COMET-Kiwi loaded: {_CHECKPOINT}")
    except Exception as e:
        print(f"⚠  COMET-Kiwi unavailable ({e}); comet_kiwi scoring will return None.")
        _model = None
    return _model


async def score_comet_kiwi_batch(units: List[TranslationUnit], gpus: int = 0) -> List[Optional[float]]:
    """Reference-free QE score per unit, native 0-1 COMET-Kiwi scale
    (caller multiplies by 100 for this system's 0-100 convention — see
    app/api/quality.py). Returns a list the same length as `units`, with
    None wherever the model is unavailable or a unit has no target_text.

    CPU by default (gpus=0) — deliberately: COMET's own README notes CPU
    inference "is functional but significantly slower," which is exactly
    why this is a batch/offline path and never a live-translation-request
    one (see app/api/quality.py's comet-score endpoint docstring)."""
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
    scores_by_index = dict(zip((i for i, _ in scorable), output.scores))

    return [scores_by_index.get(i) for i in range(len(units))]
