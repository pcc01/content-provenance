"""
Payment/checkout localization. New capability: a checkout page that only
ever shows USD pricing and only integrates US-centric processors (Stripe,
PayPal) is a real friction point for international customers, independent
of whether the surrounding page text was translated. Two separate,
low-noise signals rather than one combined heuristic, since either can be
true without the other (a shop might show EUR pricing through a
still-US-only processor, or vice versa).

Matches on the linked/inline script text the crawler already collects —
provider domain names and SDK identifiers are a stronger, lower-noise
signal than trying to detect "checkout" semantics from page copy alone.
"""

import re
from typing import Dict, List

from app.core.audit.checks.mixed_locale import _page_region_tag
from app.core.audit.crawler import CrawledPage
from app.core.audit.regions import region_from_locale_tag
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_CHECKOUT_PATH_RE = re.compile(r"cart|checkout|payment|billing|pricing", re.IGNORECASE)

_CURRENCY_SYMBOLS = {
    "$": re.compile(r"\$\s?\d"),
    "€": re.compile(r"€\s?\d|\d\s?€"),
    "£": re.compile(r"£\s?\d"),
    "¥": re.compile(r"¥\s?\d"),
    "₹": re.compile(r"₹\s?\d"),
    "₩": re.compile(r"₩\s?\d"),
    "₽": re.compile(r"₽\s?\d"),
}

# Providers/methods commonly used outside the US — presence of any of
# these is treated as "this checkout has region-aware payment support,"
# regardless of whether Stripe/PayPal are ALSO present (most sites layer
# a generic processor with local methods on top, not replace it).
_LOCALIZED_PROVIDER_RE = re.compile(
    r"klarna|adyen|mollie|alipay|wechat\s?pay|\bsepa\b|ideal\.nl|bancontact|giropay|eps[-_]?zahlung",
    re.IGNORECASE,
)


def _is_checkout_like(page: CrawledPage) -> bool:
    from urllib.parse import urlparse
    return bool(_CHECKOUT_PATH_RE.search(urlparse(page.url).path))


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        region = region_from_locale_tag(_page_region_tag(page.url, page.html_lang))
        if region in (None, "US") or not _is_checkout_like(page):
            continue
        page_id = page_ids.get(page.url)

        joined_text = " ".join(page.text_blocks)
        currencies_found = {sym for sym, pat in _CURRENCY_SYMBOLS.items() if pat.search(joined_text)}
        if currencies_found == {"$"}:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PAYMENT_LOCALIZATION,
                finding_type="usd_only_pricing_on_international_page", severity=SiteAuditSeverity.WARNING,
                summary=f"Only USD ($) pricing found on a checkout-style page targeting {region}",
                detail={"url": page.url, "region": region},
            ))

        script_text = "\n".join(page.script_texts.values())
        if not _LOCALIZED_PROVIDER_RE.search(script_text):
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PAYMENT_LOCALIZATION,
                finding_type="no_region_specific_payment_method", severity=SiteAuditSeverity.INFO,
                summary=(
                    f"No region-appropriate payment method (e.g. Klarna, Adyen, SEPA, Alipay) detected "
                    f"on a checkout-style page targeting {region} — verify local payment support"
                ),
                detail={"url": page.url, "region": region},
            ))

    return findings
