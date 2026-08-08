"""Style scorer selection — the §5 counterpart to app/core/scoring/factory.py.
No deterministic floor-check layer (unlike CompositeScorer): tone/voice/
terminology adherence isn't something a regex can pre-screen the way
untranslated-text/placeholder-leak accuracy checks can.
"""

from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.scoring.style_base import StyleScorer, StyleScoreResult
from app.models.schemas import StyleAdherenceScore, StyleContextRetrieval, TranslationUnit

_scorer_instance: Optional[StyleScorer] = None


def get_style_scorer(provider: Optional[str] = None) -> StyleScorer:
    global _scorer_instance
    requested = (provider or settings.style_scoring_provider).lower()
    if provider is None and _scorer_instance is not None:
        return _scorer_instance

    if requested == "claude":
        from app.core.scoring.style_scorer import ClaudeStyleScorer
        scorer: StyleScorer = ClaudeStyleScorer()
    else:
        raise RuntimeError(f"Unknown style scoring provider '{requested}' — expected 'claude'")

    if provider is None:
        _scorer_instance = scorer
    return scorer


async def score_unit_style(
    unit: TranslationUnit,
    style_guide_id: Optional[str] = None,
    context: Optional[StyleContextRetrieval] = None,
    scorer: Optional[StyleScorer] = None,
) -> StyleAdherenceScore:
    """Scores a unit's CURRENT target_text and persists the result — the
    style-adherence analogue of RedriveEngine._score_unit. A scorer failure
    (missing credentials, network error, unparseable response) must not
    crash the caller — same resilience the quality-scoring path already
    applies. `scorer` overrides the configured default — RedriveEngine
    passes its own injected style_scorer through here (see
    RedriveEngine.__init__), the same test-injectability
    app/core/redrive/engine.py's `scorer` param already gives QualityScorer."""
    db = get_db()
    scorer = scorer or get_style_scorer()
    try:
        result = await scorer.score_text(
            unit.target_text or "", unit.target_language, context, reference_text=unit.source_text,
        )
    except Exception as e:
        result = StyleScoreResult(reasons=["scorer_error"], raw_response=str(e), needs_review=True)

    record = StyleAdherenceScore(
        unit_id=unit.id, style_guide_id=style_guide_id,
        tone_score=result.tone_score, voice_score=result.voice_score,
        terminology_score=result.terminology_score, overall_score=result.overall_score,
        scorer=settings.style_scoring_provider, reasons=result.reasons,
        raw_response=result.raw_response, needs_review=result.needs_review,
    )
    return await db.save_style_adherence_score(record)
