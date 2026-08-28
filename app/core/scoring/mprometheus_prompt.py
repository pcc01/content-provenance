"""
M-Prometheus (Unbabel) evaluation prompt + response parsing.

Kept deliberately separate from mqm_prompt.py: M-Prometheus is trained on the
Prometheus "absolute grading" template — long-form English feedback followed
by a single integer 1-5 grade — NOT the MQM-JSON error-annotation contract
every other model scorer in this package shares. Running it on its own rubric
is where its numbers are calibrated (see docs/quality-evaluation-research.md
§9 and the card at https://huggingface.co/Unbabel/M-Prometheus-14B).

The 1-5 grade is coarse, so it is mapped onto the 0-100 band this codebase
scores in (1->20 … 5->100). hard_fail is intentionally NOT derived from it —
deterministic.py's checks (and, later, XCOMET critical spans) own that signal.
"""

import re
from typing import Optional

from app.core.scoring.base import ScoreResult

# Lifted from the model card's MT evaluation example (Accuracy / Fluency /
# Style rubric). The reference clause and blocks are omitted entirely in
# reference-free mode rather than left as empty headings.
_TEMPLATE = """###Task Description:
An instruction, a response to evaluate, {ref_clause}and a score rubric representing an evaluation criteria are given.
1. Write a detailed feedback that assesses the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5. You should refer to the score rubric.
3. The output format should look as follows: "Feedback: (write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
Translate the following text from {source_language} to {target_language}: {source}
{glossary_block}###Response to evaluate:
{hypothesis}
{reference_block}###Score Rubrics:
[Is the translation accurate, fluent, and stylistically appropriate for the target language?]
Score 1: Severely inadequate — major mistranslation or omission; meaning is lost or reversed, or the text is unusable.
Score 2: Poor — several accuracy or grammar errors a native reader would immediately notice; needs substantial rework.
Score 3: Acceptable with reservations — meaning comes through but with awkward phrasing, a minor mistranslation, or inconsistent terminology.
Score 4: Good — accurate and fluent; only minor stylistic or cosmetic issues remain.
Score 5: Excellent — accurate, natural, idiomatic, and consistent with any supplied terminology and style.

###Feedback:"""

_RESULT_RE = re.compile(r"\[RESULT\]\s*\(?\s*([1-5])")
# Fallback for models that drop the literal [RESULT] tag but still end on a grade.
_TRAILING_GRADE_RE = re.compile(r"(?:score|result)\D{0,12}([1-5])\s*(?:/\s*5)?\s*\.?\s*$", re.IGNORECASE)

_GRADE_TO_SCORE = {1: 20.0, 2: 40.0, 3: 60.0, 4: 80.0, 5: 100.0}


def build_prompt(
    source_text: str,
    source_language: str,
    target_language: str,
    hypothesis: str,
    reference: Optional[str] = None,
    glossary: Optional[str] = None,
) -> str:
    """Renders the absolute-grading prompt. `reference` (a known-good target,
    e.g. a near-exact TM hit) becomes the "Score 5" anchor when supplied;
    `glossary` is a pre-rendered block of approved terms/rules folded into
    the instruction."""
    ref_clause = "a reference answer that gets a score of 5, " if reference else ""
    reference_block = f"###Reference Answer (Score 5):\n{reference}\n\n" if reference else ""
    glossary_block = f"\nApproved terminology and style to follow:\n{glossary}\n\n" if glossary else "\n"
    return _TEMPLATE.format(
        ref_clause=ref_clause,
        source_language=source_language,
        target_language=target_language,
        source=source_text,
        hypothesis=hypothesis,
        reference_block=reference_block,
        glossary_block=glossary_block,
    )


def parse_mprometheus_response(
    raw: str, *, reference_used: bool, reference_mode: str,
) -> ScoreResult:
    """Turns M-Prometheus's `Feedback: … [RESULT] N` completion into a
    ScoreResult. Unparseable output -> needs_review rather than a guessed
    score, matching mqm_prompt.parse_mqm_response's fallback contract.

    `reference_mode`/`reference_used` are threaded in only so the scorer can
    record — in the free-form `reasons` list, since Phase 1 adds no schema —
    whether the grade was reference-grounded. `prefer_reference` with no
    reference found is surfaced as needs_review so a human knows the number
    is less anchored."""
    text = (raw or "").strip()
    match = _RESULT_RE.search(text) or _TRAILING_GRADE_RE.search(text)
    if not match:
        return ScoreResult(
            score=None, reasons=["evaluator_unparseable"], raw_response=raw, needs_review=True,
        )

    grade = int(match.group(1))
    feedback = re.split(r"\[RESULT\]", text, maxsplit=1)[0]
    feedback = re.sub(r"^\s*Feedback:\s*", "", feedback).strip()
    first_sentence = ""
    if feedback:
        first_sentence = re.split(r"(?<=[.!?])\s+", feedback)[0].strip()[:280]

    reasons = []
    if grade <= 3:
        reasons.append("evaluator_flagged")
    if first_sentence:
        reasons.append(f"mprometheus: {first_sentence}")
    reasons.append(f"reference={'used' if reference_used else 'none'} (mode={reference_mode})")

    needs_review = reference_mode == "prefer_reference" and not reference_used
    return ScoreResult(
        score=_GRADE_TO_SCORE[grade],
        reasons=reasons,
        raw_response=raw,
        needs_review=needs_review,
    )
