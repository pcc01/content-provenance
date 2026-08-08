"""Lazy sentence-transformers wrapper for Phase 13's retrieval layer —
independent of app/core/haystack_pipeline.py's own embedder (that one is
wired into a Haystack Pipeline object; this is a plain
text -> vector-or-None function the repository layer's vector-search
methods can call directly). Same EMBEDDING_MODEL setting, so both
subsystems embed into the same space, but no shared runtime state.

Degrades gracefully when sentence-transformers (or its model weights)
isn't available — same pattern as haystack_pipeline.py's HAYSTACK_AVAILABLE
flag: callers get None back and fall back to locale/keyword filtering
(see app/core/graph/retrieval.py), never an exception.
"""

import asyncio
from typing import List, Optional

from app.core.config import settings

_model = None
_load_attempted = False


def _load_model():
    global _model, _load_attempted
    if _load_attempted:
        return _model
    _load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.embedding_model)
        print(f"✓ Graph retrieval embedding model loaded: {settings.embedding_model}")
    except Exception as e:
        print(
            f"⚠  Embedding model unavailable ({e}); Phase 13 retrieval falls back to "
            "locale/keyword filtering instead of vector similarity."
        )
        _model = None
    return _model


async def embed_text(text: str) -> Optional[List[float]]:
    """None means "no embedding available" — never raises. encode() is
    synchronous/CPU-bound, so it runs off the event loop via the default
    executor rather than blocking every other in-flight request."""
    model = _load_model()
    if model is None or not text:
        return None
    loop = asyncio.get_running_loop()
    vector = await loop.run_in_executor(None, lambda: model.encode(text, normalize_embeddings=True))
    return vector.tolist()


def embeddings_available() -> bool:
    return _load_model() is not None
