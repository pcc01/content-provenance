"""
Deterministic (free, no model call) quality floor-checks — ported from
peripateticware's frontend/scripts/qa_review_llamacpp.py, trimmed to the
checks that don't depend on that project's own locale-convention tables.

Three tiers:
  HARD (0):          untranslated, garbage, broken template placeholders
  STRUCTURAL (5-10):  wrong script, altered emails/URLs, HTML tag mismatch,
                      missing numbers, suspicious truncation
  COSMETIC (85):      whitespace/newline convention drift

These run before any model call — most obviously-bad or obviously-fine pairs
never need an LLM's judgment at all. Locale-specific conventions (CLDR number/
date formatting, day-first vs month-first) from the original script are a
deliberate scope cut here, not a bug — they mattered there because of babel
integration specific to that project's locale set.
"""

import re
from typing import List, Optional, Tuple

PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\{[^{}]+\}|%[sd]|\$t\([^)]*\)")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DIGIT_RUN_RE = re.compile(r"\d+")

_CJK_RANGES = {
    "ja": [(0x3040, 0x30FF), (0x4E00, 0x9FFF)],
    "zh": [(0x4E00, 0x9FFF)],
    "ko": [(0xAC00, 0xD7A3)],
}
_RTL_RANGES = {
    "ar": [(0x0600, 0x06FF)],
    "he": [(0x0590, 0x05FF)],
}
_NONLATIN_RANGES = [(0x0400, 0x04FF), (0x0590, 0x05FF), (0x0600, 0x06FF),
                     (0x3040, 0x30FF), (0x4E00, 0x9FFF), (0xAC00, 0xD7A3)]


def _in_ranges(c: str, ranges) -> bool:
    return any(lo <= ord(c) <= hi for lo, hi in ranges)


def _has_expected_script(text: str, target_language: str) -> bool:
    base = target_language.split("-")[0].lower()
    ranges = _CJK_RANGES.get(base) or _RTL_RANGES.get(base)
    if not ranges:
        return True  # Latin-script (or unrecognized) target — nothing specific to require
    return any(_in_ranges(c, ranges) for c in text)


_JSONISH_RE = re.compile(r"^\[.*\]$|^\{.*\}$", re.DOTALL)


def _looks_like_garbage(target: str, source: str) -> bool:
    stripped = target.strip()
    if not stripped:
        return False  # handled by the untranslated check
    # Whole-string check, not "starts with a bracket" — real translations
    # legitimately start with "[" all the time (a "[Note] ...", "[1] step
    # one", or a provider's own "[IT] ..." language-tag convention), so this
    # only flags content that IS a stringified array/object end to end.
    if _JSONISH_RE.match(stripped) and not _JSONISH_RE.match(source.strip()):
        return True  # stringified array/object leaked into the translation
    if len(stripped) > max(50, len(source) * 4):
        return True  # wildly longer than the source — repetition/token spam
    words = stripped.split()
    if len(words) >= 6 and len(set(words)) == 1:
        return True  # the same token repeated over and over
    return False


def _emails_preserved(source: str, target: str) -> bool:
    return all(e in target for e in _EMAIL_RE.findall(source))


def deterministic_score(
    source_text: str, target_text: Optional[str], target_language: str,
) -> Tuple[Optional[float], List[str]]:
    """Returns (floor_score, reasons) when a free check already decides the
    verdict, or (None, []) when the pair needs a model's judgment."""
    if target_text is None or target_text.strip() == "":
        return 0, ["untranslated"]
    if target_text == source_text:
        return 0, ["untranslated"]

    src_placeholders = PLACEHOLDER_RE.findall(source_text)
    if src_placeholders and any(ph not in target_text for ph in src_placeholders):
        return 0, ["placeholder_broken"]
    if _looks_like_garbage(target_text, source_text):
        return 0, ["garbage_pattern"]

    structural: List[Tuple[int, str]] = []
    base = target_language.split("-")[0].lower()

    if not _has_expected_script(target_text, target_language):
        structural.append((5, "wrong_script"))
    elif base not in ("ja", "zh", "ko", "ar", "he"):
        foreign = sum(1 for c in target_text if _in_ranges(c, _NONLATIN_RANGES))
        if foreign > 2:
            structural.append((5, "wrong_script"))

    if not _emails_preserved(source_text, target_text):
        structural.append((5, "email_altered"))
    if any(url not in target_text for url in _URL_RE.findall(source_text)):
        structural.append((5, "url_altered"))
    if sorted(_HTML_TAG_RE.findall(source_text)) != sorted(_HTML_TAG_RE.findall(target_text)):
        structural.append((10, "html_tag_mismatch"))

    src_runs = _DIGIT_RUN_RE.findall(source_text)
    if src_runs:
        remaining = list(_DIGIT_RUN_RE.findall(target_text))
        for run in src_runs:
            if run in remaining:
                remaining.remove(run)
            else:
                structural.append((10, "number_mismatch"))
                break

    if base not in ("ja", "zh", "ko") and len(source_text) >= 30 and \
            len(target_text.strip()) < max(4, int(0.15 * len(source_text))):
        structural.append((10, "suspicious_truncation"))

    if structural:
        return min(s for s, _ in structural), sorted({r for _, r in structural})

    cosmetic: List[str] = []
    if (source_text[:1].isspace() != target_text[:1].isspace()) or \
       (source_text[-1:].isspace() != target_text[-1:].isspace()):
        cosmetic.append("whitespace_mismatch")
    if source_text.count("\n") != target_text.count("\n"):
        cosmetic.append("newline_count_mismatch")

    if cosmetic:
        return 85, sorted(set(cosmetic))

    return None, []
