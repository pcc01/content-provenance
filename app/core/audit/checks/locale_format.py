"""
Phase 12 — hardcoded locale-format assumptions. New capability: US-centric
form validation (5-digit zip regex, a US-state dropdown, a 10-digit phone
pattern) and hardcoded US-style currency/date formatting are classic,
easy-to-miss expansion blockers — a form that silently rejects every
non-US postal code, or a date that's ambiguous (03/04 — March 4th or April
3rd?) outside the US, is a real usability failure, not a translation gap.
"""

import re
from typing import Dict, List

from app.core.audit.checks.mixed_locale import _page_region_tag
from app.core.audit.crawler import CrawledPage
from app.core.audit.regions import region_from_locale_tag
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY",
}
_MIN_STATE_OVERLAP_TO_FLAG = 15  # a coincidental handful of 2-letter codes isn't a US state dropdown

_ZIP_FIELD_NAME_RE = re.compile(r"zip|postal", re.IGNORECASE)
# Matches the LITERAL text of an HTML pattern attribute, e.g. "[0-9]{5}" or
# "\d{5}" — \\d below matches a literal backslash-d in the target string,
# not the regex digit-shorthand (which would instead match any single digit
# character and silently fail to find a real HTML pattern="\d{5}" string).
_US_ZIP_PATTERN_RE = re.compile(r"^(\[?0-9\]?|\\d)\{5\}")
_PHONE_FIELD_NAME_RE = re.compile(r"phone|tel(?:ephone)?", re.IGNORECASE)
_US_PHONE_PATTERN_RE = re.compile(r"\\d\{3\}.*\\d\{3\}.*\\d\{4\}")

_US_DOLLAR_RE = re.compile(r"\$\s?\d")
_AMBIGUOUS_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_MIN_OCCURRENCES_TO_FLAG = 3


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        page_id = page_ids.get(page.url)
        region = region_from_locale_tag(_page_region_tag(page.url, page.html_lang))

        for select in page.selects:
            options = {o.strip().upper() for o in select.get("options", [])}
            if len(options & _US_STATE_ABBREVIATIONS) >= _MIN_STATE_OVERLAP_TO_FLAG and region not in (None, "US"):
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_FORMAT,
                    finding_type="us_state_dropdown_on_non_us_page", severity=SiteAuditSeverity.WARNING,
                    summary=f"A US-state dropdown ({select.get('name') or 'unnamed field'}) appears on a page targeting {region}",
                    detail={"url": page.url, "field": select.get("name"), "region": region},
                ))

        for inp in page.form_inputs:
            name = inp.get("name", "")
            pattern = inp.get("pattern", "")
            maxlength = inp.get("maxlength", "")
            if _ZIP_FIELD_NAME_RE.search(name) and region not in (None, "US"):
                if _US_ZIP_PATTERN_RE.search(pattern) or maxlength == "5":
                    findings.append(SiteAuditFinding(
                        audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_FORMAT,
                        finding_type="us_centric_postal_code_field", severity=SiteAuditSeverity.WARNING,
                        summary=f"Postal-code field ({name}) only accepts 5-digit US zip codes, on a page targeting {region}",
                        detail={"url": page.url, "field": name, "pattern": pattern, "maxlength": maxlength, "region": region},
                    ))
            if _PHONE_FIELD_NAME_RE.search(name) and _US_PHONE_PATTERN_RE.search(pattern) and region not in (None, "US"):
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_FORMAT,
                    finding_type="us_centric_phone_format", severity=SiteAuditSeverity.WARNING,
                    summary=f"Phone field ({name}) only accepts a 10-digit US format, on a page targeting {region}",
                    detail={"url": page.url, "field": name, "pattern": pattern, "region": region},
                ))

        if region not in (None, "US"):
            joined_text = " ".join(page.text_blocks)
            dollar_hits = len(_US_DOLLAR_RE.findall(joined_text))
            date_hits = len(_AMBIGUOUS_DATE_RE.findall(joined_text))
            if dollar_hits >= _MIN_OCCURRENCES_TO_FLAG:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_FORMAT,
                    finding_type="hardcoded_dollar_currency", severity=SiteAuditSeverity.INFO,
                    summary=f"{dollar_hits} literal $-prefixed price(s) found on a page targeting {region}",
                    detail={"url": page.url, "count": dollar_hits, "region": region},
                ))
            if date_hits >= _MIN_OCCURRENCES_TO_FLAG:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_FORMAT,
                    finding_type="ambiguous_date_format", severity=SiteAuditSeverity.INFO,
                    summary=f"{date_hits} numeric date(s) in an ambiguous MM/DD-style format found on a page targeting {region}",
                    detail={"url": page.url, "count": date_hits, "region": region},
                ))

    return findings
