"""
Phase 11 — ICU / i18n-tooling detection. New capability, no existing
script to port: greps a page's script bodies for known i18n library
signatures (react-intl, i18next, Intl.* APIs, ...) and separately greps
the page's own RENDERED TEXT for literal, unparsed ICU MessageFormat
syntax (e.g. "{count, plural, one {...} other {...}}") — the latter is a
real visible bug if it leaks into what a visitor actually sees, and is the
highest-value finding this check can produce.
"""

import re
from typing import Dict, List

from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_LIBRARY_SIGNATURES = {
    "react-intl / FormatJS": re.compile(r"react-intl|@formatjs|FormatJS"),
    "i18next": re.compile(r"\bi18next\b"),
    "vue-i18n": re.compile(r"\bvue-i18n\b"),
    "messageformat.js": re.compile(r"\bmessageformat\b", re.IGNORECASE),
    "Angular $localize": re.compile(r"\$localize\b"),
    "gettext-style": re.compile(r"\b(?:n?gettext)\s*\("),
    "Globalize.js": re.compile(r"\bGlobalize\b"),
    "Polyglot.js": re.compile(r"\bPolyglot\b"),
    "Intl.NumberFormat": re.compile(r"Intl\.NumberFormat"),
    "Intl.DateTimeFormat": re.compile(r"Intl\.DateTimeFormat"),
    "Intl.PluralRules": re.compile(r"Intl\.PluralRules"),
    "Intl.RelativeTimeFormat": re.compile(r"Intl\.RelativeTimeFormat"),
    "Intl.ListFormat": re.compile(r"Intl\.ListFormat"),
    "Intl.Segmenter": re.compile(r"Intl\.Segmenter"),
}

# Literal ICU MessageFormat syntax — if this shows up in rendered text, the
# message was never run through a formatter before display.
_ICU_SYNTAX_RE = re.compile(r"\{\s*\w+\s*,\s*(plural|select|selectordinal)\s*,")


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        page_id = page_ids.get(page.url)
        combined_scripts = "\n".join(page.script_texts.values())

        detected = [name for name, pat in _LIBRARY_SIGNATURES.items() if pat.search(combined_scripts)]
        if detected:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.ICU_I18N,
                finding_type="icu_library_detected", severity=SiteAuditSeverity.INFO,
                summary=f"i18n tooling detected: {', '.join(detected)}",
                detail={"url": page.url, "libraries": detected},
            ))

        for block in page.text_blocks:
            match = _ICU_SYNTAX_RE.search(block)
            if match:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.ICU_I18N,
                    finding_type="icu_syntax_leak", severity=SiteAuditSeverity.CRITICAL,
                    summary="Unparsed ICU MessageFormat syntax visible in rendered page text",
                    detail={"url": page.url, "snippet": block[:200]},
                ))
                break  # one leak finding per page is enough to flag it for review

    return findings
