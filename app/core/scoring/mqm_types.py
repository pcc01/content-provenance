"""Official MQM-Core error typology — sourced directly from the MQM
Council's own workbooks (themqm.org/resources/): the "MQM-Core" sheet of
`2024_03-07-MQMFull_Master-Official.xlsx`, cross-referenced against that
same file's "MQMFull Master" sheet for each item's official mnemonic Error
Type ID (e.g. "mistranslation" for PID MQMC_101000). See
docs/quality-evaluation-research.md §8.2 for the full provenance.

Both source workbooks are stamped "© 2024 MQM, content created by The MQM
Council... openly licensed via CC" — free to use, not a commercial-use
restriction the way COMET's model weights are (see comet_kiwi.py).

7 dimensions + 37 subtypes = 44 total error types. Dimension-level members
are valid on their own — MQM explicitly allows flagging at just the top
level ("For many production environments, the top-level 'dimensions' may
be sufficient", themqm.org/about-us/) — not every flagged error needs a
Level-2 subtype.
"""

from enum import Enum
from typing import Dict


class MQMDimension(str, Enum):
    TERMINOLOGY = "terminology"
    ACCURACY = "accuracy"
    LINGUISTIC_CONVENTIONS = "fluency"           # MQM 1.0 name: "Fluency"
    STYLE = "style"
    LOCALE_CONVENTIONS = "locale-conventions"
    AUDIENCE_APPROPRIATENESS = "verity"          # MQM 1.0 name: "Verity"
    DESIGN_AND_MARKUP = "design"


class MQMErrorType(str, Enum):
    """Value = the official MQM mnemonic Error Type ID."""
    # Terminology
    TERMINOLOGY = "terminology"
    TERMBASE = "termbase"
    TERM_INCONSISTENCY = "term-inconsistency"
    WRONG_TERM = "wrong-term"
    # Accuracy
    ACCURACY = "accuracy"
    MISTRANSLATION = "mistranslation"
    OVER_TRANSLATION = "over-translation"
    UNDER_TRANSLATION = "under-translation"
    ADDITION = "addition"
    OMISSION = "omission"
    NO_TRANSLATE = "no-translate"
    UNTRANSLATED = "untranslated"
    # Linguistic Conventions
    FLUENCY = "fluency"
    GRAMMAR = "grammar"
    UNINTELLIGIBLE = "unintelligible"
    CHARACTER_ENCODING = "character-encoding"
    TEXTUAL_CONVENTIONS = "textual-conventions"
    # Style
    STYLE = "style"
    COMPANY_STYLE = "company-style"
    THIRD_PARTY_STYLE = "third-party-style"
    INCONSISTENT_EXTERNAL_REFERENCE = "inconsistent-external-reference"
    REGISTER = "register"
    AWKWARD = "awkward"
    UNIDIOMATIC = "unidiomatic"
    INCONSISTENT_STYLE = "inconsistent-style"
    # Locale Conventions
    LOCALE_CONVENTIONS = "locale-conventions"
    NUMBER_FORMAT = "number-format"
    CURRENCY_FORMAT = "currency-format"
    MEASUREMENT_FORMAT = "measurement-format"
    TIME_FORMAT = "time-format"
    DATE_FORMAT = "date-format"
    ADDRESS_FORMAT = "address-format"
    TELEPHONE_FORMAT = "telephone-format"
    SHORTCUT_KEY = "shortcut-key"
    # Audience Appropriateness
    VERITY = "verity"
    CULTURE_SPECIFIC = "culture-specific"
    OFFENSIVE = "offensive"
    # Design and Markup
    DESIGN = "design"
    LOCAL_FORMATTING = "local-formatting"
    OVERALL_DESIGN = "overall-design"
    MARKUP = "markup"
    TRUNCATION_TEXT_EXPANSION = "truncation-text-expansion"
    MISSING_TEXT = "missing-text"
    BROKEN_LINK = "broken-link"


# Every MQMErrorType's parent dimension — used to render a dimension-
# grouped rubric into the scorer prompt (see claude_scorer.py) and to
# group/report errors by dimension without a second lookup table.
MQM_ERROR_TYPE_DIMENSION: Dict[MQMErrorType, MQMDimension] = {
    MQMErrorType.TERMINOLOGY: MQMDimension.TERMINOLOGY,
    MQMErrorType.TERMBASE: MQMDimension.TERMINOLOGY,
    MQMErrorType.TERM_INCONSISTENCY: MQMDimension.TERMINOLOGY,
    MQMErrorType.WRONG_TERM: MQMDimension.TERMINOLOGY,

    MQMErrorType.ACCURACY: MQMDimension.ACCURACY,
    MQMErrorType.MISTRANSLATION: MQMDimension.ACCURACY,
    MQMErrorType.OVER_TRANSLATION: MQMDimension.ACCURACY,
    MQMErrorType.UNDER_TRANSLATION: MQMDimension.ACCURACY,
    MQMErrorType.ADDITION: MQMDimension.ACCURACY,
    MQMErrorType.OMISSION: MQMDimension.ACCURACY,
    MQMErrorType.NO_TRANSLATE: MQMDimension.ACCURACY,
    MQMErrorType.UNTRANSLATED: MQMDimension.ACCURACY,

    MQMErrorType.FLUENCY: MQMDimension.LINGUISTIC_CONVENTIONS,
    MQMErrorType.GRAMMAR: MQMDimension.LINGUISTIC_CONVENTIONS,
    MQMErrorType.UNINTELLIGIBLE: MQMDimension.LINGUISTIC_CONVENTIONS,
    MQMErrorType.CHARACTER_ENCODING: MQMDimension.LINGUISTIC_CONVENTIONS,
    MQMErrorType.TEXTUAL_CONVENTIONS: MQMDimension.LINGUISTIC_CONVENTIONS,

    MQMErrorType.STYLE: MQMDimension.STYLE,
    MQMErrorType.COMPANY_STYLE: MQMDimension.STYLE,
    MQMErrorType.THIRD_PARTY_STYLE: MQMDimension.STYLE,
    MQMErrorType.INCONSISTENT_EXTERNAL_REFERENCE: MQMDimension.STYLE,
    MQMErrorType.REGISTER: MQMDimension.STYLE,
    MQMErrorType.AWKWARD: MQMDimension.STYLE,
    MQMErrorType.UNIDIOMATIC: MQMDimension.STYLE,
    MQMErrorType.INCONSISTENT_STYLE: MQMDimension.STYLE,

    MQMErrorType.LOCALE_CONVENTIONS: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.NUMBER_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.CURRENCY_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.MEASUREMENT_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.TIME_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.DATE_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.ADDRESS_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.TELEPHONE_FORMAT: MQMDimension.LOCALE_CONVENTIONS,
    MQMErrorType.SHORTCUT_KEY: MQMDimension.LOCALE_CONVENTIONS,

    MQMErrorType.VERITY: MQMDimension.AUDIENCE_APPROPRIATENESS,
    MQMErrorType.CULTURE_SPECIFIC: MQMDimension.AUDIENCE_APPROPRIATENESS,
    MQMErrorType.OFFENSIVE: MQMDimension.AUDIENCE_APPROPRIATENESS,

    MQMErrorType.DESIGN: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.LOCAL_FORMATTING: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.OVERALL_DESIGN: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.MARKUP: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.TRUNCATION_TEXT_EXPANSION: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.MISSING_TEXT: MQMDimension.DESIGN_AND_MARKUP,
    MQMErrorType.BROKEN_LINK: MQMDimension.DESIGN_AND_MARKUP,
}


def build_prompt_rubric() -> str:
    """Renders a compact, dimension-grouped rubric for the Claude scorer's
    system prompt — the full 44-item taxonomy with descriptions would bloat
    every scoring call, so this gives just the mnemonic IDs grouped by
    dimension, enough for the model to pick a plausible value without
    needing the full MQM workbook in context."""
    by_dim: Dict[MQMDimension, list] = {d: [] for d in MQMDimension}
    for error_type, dim in MQM_ERROR_TYPE_DIMENSION.items():
        if error_type.value != dim.value:  # skip the dimension-level entry itself here
            by_dim[dim].append(error_type.value)
    lines = []
    for dim in MQMDimension:
        lines.append(f"  {dim.value} ({dim.name.replace('_', ' ').title()}): {', '.join(by_dim[dim])}")
    return "\n".join(lines)
