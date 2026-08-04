"""
Quality scoring — the "assess" half of threshold-quality redrive.

Score 0-100, lower = worse (peripateticware's convention). RedriveEngine
(app/core/redrive/engine.py) uses the score to decide what crosses a
threshold and needs to be resent for translation.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.schemas import ScoreError, TranslationUnit


class ScoreResult(BaseModel):
    score: Optional[float] = Field(None, ge=0.0, le=100.0)  # None = evaluator couldn't score it
    reasons: List[str] = Field(default_factory=list)
    errors: List[ScoreError] = Field(default_factory=list)
    raw_response: Optional[str] = None
    deterministic: bool = False
    needs_review: bool = False


class QualityScorer(ABC):
    @abstractmethod
    async def score(self, unit: TranslationUnit) -> ScoreResult:
        ...
