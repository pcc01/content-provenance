"""METEOR — a lightweight, non-LLM lexical MT-quality metric (Banerjee &
Lavie, "METEOR: An Automatic Metric for MT Evaluation with Improved
Correlation with Human Judgments," ACL 2005 — Alon Lavie co-created it;
see docs/quality-evaluation-research.md §4). Unigram precision/recall with
stemmed/synonym matching plus a fragmentation penalty — pure CPU
computation via NLTK, no model weights, no network call at score time
(only a one-time WordNet corpus download).

METEOR needs a REFERENCE translation, which most units in this system
don't have as a first-class concept (source + AI-produced target, no
independent human reference). Per §4.5/§7.2 of the research doc, this is
scoped specifically to **redrive regression-checking**: comparing a new
candidate translation against the PREVIOUS, already-approved version as a
pseudo-reference — informational only, never a redrive-blocking gate (see
RedriveEngine._record_meteor_regression).
"""

import asyncio
from typing import Optional

_wordnet_ready = False


def _ensure_wordnet() -> None:
    global _wordnet_ready
    if _wordnet_ready:
        return
    import nltk
    for corpus in ("corpora/wordnet", "corpora/omw-1.4"):
        try:
            nltk.data.find(corpus)
        except LookupError:
            nltk.download(corpus.split("/")[-1], quiet=True)
    _wordnet_ready = True


def meteor_available() -> bool:
    try:
        import nltk  # noqa: F401
        from nltk.translate import meteor_score  # noqa: F401
    except ImportError:
        return False
    return True


async def compute_meteor(hypothesis: str, reference: str) -> Optional[float]:
    """Returns a 0-100 METEOR score, or None if nltk isn't installed —
    same graceful-degradation pattern as app/core/graph/embeddings.py's
    embed_text (never raises). meteor_score() is synchronous/CPU-bound,
    so it runs off the event loop via the default executor."""
    if not hypothesis or not reference:
        return None
    if not meteor_available():
        return None

    loop = asyncio.get_running_loop()

    def _score() -> float:
        from nltk.translate.meteor_score import meteor_score
        _ensure_wordnet()
        return meteor_score([reference.split()], hypothesis.split())

    raw = await loop.run_in_executor(None, _score)
    return round(raw * 100, 2)
