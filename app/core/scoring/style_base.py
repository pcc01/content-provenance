"""Style/tone/voice adherence scoring — the §5 counterpart to
app/core/scoring/base.py's accuracy-focused QualityScorer. Same 0-100,
lower-is-worse convention, three sub-axes instead of one.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.schemas import StyleContextRetrieval


class StyleScoreResult(BaseModel):
    tone_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    voice_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    terminology_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    overall_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    reasons: List[str] = Field(default_factory=list)
    raw_response: Optional[str] = None
    needs_review: bool = False


class StyleScorer(ABC):
    @abstractmethod
    async def score_text(
        self,
        text: str,
        language: str,
        context: Optional[StyleContextRetrieval] = None,
        reference_text: Optional[str] = None,
    ) -> StyleScoreResult:
        """Judge `text` for tone/voice/terminology adherence — `text` can be
        a translation OR a source-language draft (§9b.5's source-side voice
        check reuses the same scorer this way, before translation even
        happens). `reference_text`, when given, is the source `text` was
        translated from — purely for context, never judged for accuracy
        (that's QualityScorer's job, kept deliberately separate)."""
        ...
