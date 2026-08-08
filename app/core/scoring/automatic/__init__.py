"""Phase 15 — non-LLM automatic MT-quality metrics: METEOR and COMET-Kiwi.
Independent of app/core/scoring/'s LLM-judge scorers (ClaudeQualityScorer,
ClaudeStyleScorer) — a third axis, never blended into either's score. See
docs/quality-evaluation-research.md §7 and AutomaticMetricScoreRow's
docstring (app/core/db/models.py).
"""
