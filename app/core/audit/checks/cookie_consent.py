"""
Phase 12 — cookie-consent mechanism detection. New capability, and the
first check that reasons about WHICH regulation applies to a page rather
than a single generic "does a privacy policy exist": GDPR/UK GDPR/LGPD-
style regimes require an affirmative consent mechanism for non-essential
cookies, not just a link to a policy. Detects known consent-management
platforms by script signature, with a lower-confidence text-based fallback
for hand-rolled banners.
"""

import re
from typing import Dict, List

from app.core.audit.checks.mixed_locale import _page_region_tag
from app.core.audit.crawler import CrawledPage
from app.core.audit.regions import region_from_locale_tag, requires_cookie_consent
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_CMP_SIGNATURES = {
    "OneTrust": re.compile(r"onetrust|cookielaw\.org", re.IGNORECASE),
    "Cookiebot": re.compile(r"cookiebot", re.IGNORECASE),
    "Quantcast Choice": re.compile(r"quantcast\.mgr\.consensu|quantcast choice", re.IGNORECASE),
    "TrustArc": re.compile(r"trustarc|truste\.com", re.IGNORECASE),
    "Osano": re.compile(r"osano", re.IGNORECASE),
    "Termly": re.compile(r"termly", re.IGNORECASE),
    "CookieYes": re.compile(r"cookieyes", re.IGNORECASE),
    "Iubenda": re.compile(r"iubenda", re.IGNORECASE),
    "Complianz (WordPress)": re.compile(r"complianz", re.IGNORECASE),
    "WP Cookie Consent / GDPR CP (WordPress)": re.compile(r"wp-cookie-consent|cookie-law-info|gdpr-cookie", re.IGNORECASE),
}

_BANNER_TEXT_RE = re.compile(r"we use cookies|this site uses cookies|accept cookies|cookie settings|manage cookies", re.IGNORECASE)


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        page_id = page_ids.get(page.url)
        region = region_from_locale_tag(_page_region_tag(page.url, page.html_lang))
        if not requires_cookie_consent(region):
            continue

        combined_scripts = "\n".join(page.script_texts.values())
        detected_cmp = next((name for name, pat in _CMP_SIGNATURES.items() if pat.search(combined_scripts)), None)
        has_banner_text = any(_BANNER_TEXT_RE.search(b) for b in page.text_blocks)

        if detected_cmp:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.COOKIE_CONSENT,
                finding_type="cookie_consent_mechanism_detected", severity=SiteAuditSeverity.INFO,
                summary=f"{detected_cmp} consent management platform detected ({region} requires consent)",
                detail={"url": page.url, "region": region, "cmp": detected_cmp},
            ))
        elif has_banner_text:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.COOKIE_CONSENT,
                finding_type="cookie_banner_text_detected", severity=SiteAuditSeverity.INFO,
                summary=f"Cookie-banner-like text found, no known CMP signature ({region} requires consent — verify manually)",
                detail={"url": page.url, "region": region},
            ))
        else:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.COOKIE_CONSENT,
                finding_type="missing_cookie_consent_mechanism", severity=SiteAuditSeverity.CRITICAL,
                summary=f"No cookie-consent mechanism detected on a page in a region requiring one ({region})",
                detail={"url": page.url, "region": region},
            ))

    return findings
