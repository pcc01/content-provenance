"""CometKiwi word-level QE (Phase 6 follow-up) — binary OK/BAD tags per MT
token, from a quality-estimation checkpoint with a word-level head. Turns the
BAD tokens into `error_spans` entries so they surface in the report the same
way XCOMET's do.

Sentence-level `wmt22-cometkiwi-da` (comet_kiwi.py) has no word-level head;
the WMT24 QE Task-2 baseline does. Same lazy-import / degrade-to-None /
CC-BY-NC-SA-4.0 contract as comet_kiwi.py and xcomet.py — not exercised in
CI (no unbabel-comet), the attach flow is covered with a monkeypatch.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from app.models.schemas import TranslationUnit

_CHECKPOINT = os.getenv("COMETKIWI_WORDLEVEL_CHECKPOINT", "Unbabel/WMT24-QE-task2-baseline")
_model = None
_load_attempted = False


def qe_wordlevel_available() -> bool:
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

        _model = load_from_checkpoint(download_model(_CHECKPOINT))
        print(f"✓ CometKiwi word-level QE loaded: {_CHECKPOINT}")
    except Exception as e:
        print(f"⚠  CometKiwi word-level QE unavailable ({e}); returning None.")
        _model = None
    return _model


def _bad_spans(mt: str, tags: Any) -> List[Dict[str, Any]]:
    """Map a sequence of per-token OK/BAD tags onto character spans of `mt`.
    Whitespace-token alignment; a BAD tag becomes a major-severity span."""
    if not tags:
        return []
    tokens = mt.split()
    spans: List[Dict[str, Any]] = []
    cursor = 0
    for i, tok in enumerate(tokens):
        start = mt.find(tok, cursor)
        if start < 0:
            start = cursor
        end = start + len(tok)
        cursor = end
        tag = tags[i] if i < len(tags) else "OK"
        if str(tag).upper().startswith("BAD"):
            spans.append({"text": tok, "severity": "major", "start": start, "end": end})
    return spans


async def score_cometkiwi_wordlevel_batch(
    units: List[TranslationUnit], gpus: int = 0,
) -> List[Optional[Dict[str, Any]]]:
    """Per unit: {"score": 0-1, "spans": [...]} or None where the model is
    unavailable / a unit has no target_text."""
    model = _load_model()
    if model is None:
        return [None] * len(units)

    scorable = [(i, u) for i, u in enumerate(units) if u.target_text]
    if not scorable:
        return [None] * len(units)

    data = [{"src": u.source_text, "mt": u.target_text} for _, u in scorable]
    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(None, lambda: model.predict(data, batch_size=8, gpus=gpus))

    meta = getattr(output, "metadata", None)
    mt_tags = None
    for attr in ("mt_tags", "target_tags", "word_tags", "tags"):
        mt_tags = getattr(meta, attr, None) if meta is not None else None
        if mt_tags:
            break

    results: Dict[int, Dict[str, Any]] = {}
    for local_idx, (orig_idx, unit) in enumerate(scorable):
        tags = mt_tags[local_idx] if mt_tags and local_idx < len(mt_tags) else None
        results[orig_idx] = {
            "score": output.scores[local_idx],
            "spans": _bad_spans(unit.target_text or "", tags),
        }
    return [results.get(i) for i in range(len(units))]
