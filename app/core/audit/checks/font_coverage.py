"""
Phase 12 — font/glyph coverage heuristic. New capability: a page targeting
a language written in a non-Latin script (Arabic, CJK, Devanagari, Thai,
Hebrew) needs a font that actually covers that script — a generic Latin
webfont renders missing glyphs as tofu boxes. Not real glyph-table parsing
(no font-file download/inspection, no new heavy dependency) — a
lightweight signal: does any declared font-family name look like it covers
the required script? Limited to scripts that commonly DON'T ride along
with mainstream Latin webfonts; Cyrillic/Greek are deliberately excluded
since most modern web fonts (Roboto, Open Sans, Arial, system-ui, ...)
already include those glyphs, which would make this check mostly noise.
"""

from typing import Dict, List, Optional

from app.core.audit.checks.mixed_locale import _locale_from_path
from app.core.audit.crawler import CrawledPage
from app.core.audit.source_attribution import attribute_source
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_SCRIPT_LANGUAGES = {
    "ar": "Arabic", "fa": "Arabic", "ur": "Arabic",
    "he": "Hebrew",
    "zh": "CJK", "ja": "CJK", "ko": "CJK",
    "hi": "Devanagari", "mr": "Devanagari", "ne": "Devanagari",
    "th": "Thai",
}

_SCRIPT_FONT_HINTS = {
    "Arabic": ["arabic", "tahoma", "arial unicode", "cairo", "amiri", "noto sans ar", "geeza"],
    "Hebrew": ["hebrew", "arial hebrew", "noto sans he", "david"],
    "CJK": [
        "noto sans sc", "noto sans tc", "noto sans jp", "noto sans kr", "noto sans cjk",
        "microsoft yahei", "simsun", "simhei", "pingfang", "hiragino", "malgun gothic",
        "meiryo", "source han", "yu gothic", "ms gothic",
    ],
    "Devanagari": ["devanagari", "mangal", "nirmala"],
    "Thai": ["thai", "leelawadee", "tahoma", "cordia"],
}


def _extract_font_families(css_text: str) -> List[str]:
    import re
    families = []
    for match in re.finditer(r"font-family\s*:\s*([^;{}]+)", css_text, re.IGNORECASE):
        for name in match.group(1).split(","):
            families.append(name.strip().strip("'\"").lower())
    return families


def _page_script(page: CrawledPage, audit_primary: str) -> Optional[str]:
    from urllib.parse import urlparse
    lang = _locale_from_path(urlparse(page.url).path) or (page.html_lang or "").split("-")[0].lower() or audit_primary
    return _SCRIPT_LANGUAGES.get(lang)


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []
    audit_primary = audit.primary_language.split("-")[0].lower()

    for page in pages:
        script = _page_script(page, audit_primary)
        if not script:
            continue
        families = [f for css in page.stylesheet_texts.values() for f in _extract_font_families(css)]
        hints = _SCRIPT_FONT_HINTS.get(script, [])
        covered = any(hint in family for family in families for hint in hints)
        if covered:
            continue

        # There's no single "offending" source for an ABSENCE — instead,
        # list which sources declared font-family at all, so the fix
        # ("add a script-covering fallback") has a concrete place to land
        # rather than just "somewhere in your CSS."
        font_sources = [
            {"url": url, **attribute_source(url, page.url).as_dict()}
            for url, css in page.stylesheet_texts.items() if _extract_font_families(css)
        ]

        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=page_ids.get(page.url), check=SiteAuditCheck.FONT_COVERAGE,
            finding_type="possible_missing_script_font", severity=SiteAuditSeverity.WARNING,
            summary=f"Page targets {script} script but no {script}-covering font-family was declared",
            detail={
                "url": page.url, "script": script, "declared_fonts": sorted(set(families))[:10],
                "font_declaration_sources": font_sources[:5],
            },
        ))

    return findings
