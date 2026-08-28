"""Tests for the M-Prometheus judge — prompt construction, the 1-5 -> 0-100
grade parse, and reference-mode plumbing. Pure/offline: no Ollama, no
network. Mirrors tests/test_mqm.py's convention.
Run with: PYTHONPATH=. pytest tests/test_mprometheus.py -v
"""

import pytest

from app.core.scoring.mprometheus_prompt import build_prompt, parse_mprometheus_response
from app.core.scoring.mprometheus_scorer import (
    VALID_REFERENCE_MODES,
    MPrometheusQualityScorer,
    _resolve_reference_and_glossary,
)
from app.models.schemas import TranslationMethod, TranslationUnit

# ── prompt ─────────────────────────────────────────────────────────────────

def test_prompt_reference_free_omits_reference_scaffolding():
    prompt = build_prompt("Hello", "English", "French", "Bonjour")
    assert "Reference Answer" not in prompt
    assert "a reference answer that gets a score of 5" not in prompt
    assert "Translate the following text from English to French: Hello" in prompt
    assert prompt.rstrip().endswith("###Feedback:")


def test_prompt_with_reference_anchors_score_5():
    prompt = build_prompt("Hello", "English", "French", "Salut", reference="Bonjour")
    assert "###Reference Answer (Score 5):\nBonjour" in prompt
    assert "a reference answer that gets a score of 5" in prompt


def test_prompt_folds_in_glossary_block():
    prompt = build_prompt(
        "Open the dashboard", "English", "German", "Öffnen Sie das Dashboard",
        glossary="- 'dashboard' -> 'Dashboard' (de)",
    )
    assert "Approved terminology and style to follow:" in prompt
    assert "'dashboard' -> 'Dashboard'" in prompt


# ── parse ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("grade,expected", [(1, 20.0), (2, 40.0), (3, 60.0), (4, 80.0), (5, 100.0)])
def test_grade_maps_onto_0_100_band(grade, expected):
    raw = f"Feedback: Some assessment prose here. [RESULT] {grade}"
    result = parse_mprometheus_response(raw, reference_used=False, reference_mode="auto")
    assert result.score == expected
    assert result.raw_response == raw


def test_low_grade_flags_for_redrive():
    result = parse_mprometheus_response(
        "Feedback: Meaning is reversed. [RESULT] 2", reference_used=False, reference_mode="auto",
    )
    assert "evaluator_flagged" in result.reasons
    assert any(r.startswith("mprometheus: ") for r in result.reasons)


def test_high_grade_does_not_flag():
    result = parse_mprometheus_response(
        "Feedback: Accurate and idiomatic. [RESULT] 5", reference_used=True, reference_mode="auto",
    )
    assert "evaluator_flagged" not in result.reasons
    assert "reference=used (mode=auto)" in result.reasons


def test_unparseable_output_is_needs_review_not_a_guess():
    result = parse_mprometheus_response("the model rambled and never graded", reference_used=False, reference_mode="auto")
    assert result.score is None
    assert result.needs_review is True
    assert "evaluator_unparseable" in result.reasons


def test_prefer_reference_without_a_reference_sets_needs_review():
    result = parse_mprometheus_response(
        "Feedback: Fine. [RESULT] 4", reference_used=False, reference_mode="prefer_reference",
    )
    assert result.score == 80.0
    assert result.needs_review is True


def test_missing_result_tag_falls_back_to_trailing_grade():
    result = parse_mprometheus_response("Feedback: Adequate overall. Score: 3/5", reference_used=False, reference_mode="auto")
    assert result.score == 60.0


# ── reference-mode plumbing ────────────────────────────────────────────────

def test_reference_free_mode_skips_retrieval(monkeypatch):
    scorer = MPrometheusQualityScorer(reference_mode="reference_free")
    assert scorer.reference_mode == "reference_free"


def test_unknown_reference_mode_falls_back_to_auto():
    assert MPrometheusQualityScorer(reference_mode="nonsense").reference_mode == "auto"
    assert "auto" in VALID_REFERENCE_MODES


@pytest.mark.asyncio
async def test_resolve_reference_free_returns_nothing_without_touching_retrieval():
    unit = TranslationUnit(
        source_id="s1", source_text="Hello", source_language="en-US",
        target_text="Bonjour", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id="a1",
    )
    reference, glossary = await _resolve_reference_and_glossary(unit, "reference_free")
    assert reference is None and glossary is None
