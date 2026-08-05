"""
Translation coverage / parity. New capability, aimed at sites that HAVE
already localized (unlike most of this toolkit's other checks, which fire
on English-only sites too): compares how many crawled pages live under
each locale path against the primary/unprefixed group. A French mirror
that's a fraction of the English site's page count means large parts of
the site are simply unreachable to French visitors — a concrete,
quotable gap ("60% of your site doesn't exist in French") independent of
any translation-quality judgment.

Site-level, not per-page — findings carry page_id=None, same convention
SiteAuditFinding already allows for cross-page findings (see privacy.py's
privacy_language_mismatch, which spans two pages).
"""

from collections import defaultdict
from typing import Dict, List
from urllib.parse import urlparse

from app.core.audit.checks.mixed_locale import _locale_from_path
from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

# Below this many primary-language pages, a ratio isn't meaningful — a
# 3-page crawl comparing 1 vs 1 page says nothing about real coverage.
_MIN_PRIMARY_PAGES_TO_FLAG = 2
_WARNING_RATIO = 1 / 3   # less than a third of primary's page count
_INFO_RATIO = 2 / 3      # less than two-thirds


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    groups: Dict[str, List[CrawledPage]] = defaultdict(list)
    for page in pages:
        locale = _locale_from_path(urlparse(page.url).path)
        groups["_primary_" if locale is None else locale].append(page)

    primary = groups.get("_primary_", [])
    if len(primary) < _MIN_PRIMARY_PAGES_TO_FLAG:
        return findings  # crawl too shallow, or site isn't structured with a locale-prefixed primary group

    for locale, group in groups.items():
        if locale == "_primary_":
            continue
        ratio = len(group) / len(primary)
        if ratio >= _INFO_RATIO:
            continue
        severity = SiteAuditSeverity.WARNING if ratio < _WARNING_RATIO else SiteAuditSeverity.INFO
        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=None, check=SiteAuditCheck.TRANSLATION_COVERAGE,
            finding_type="translation_coverage_gap", severity=severity,
            summary=(
                f"/{locale}/ has {len(group)} of the {len(primary)} pages found in the primary "
                f"language ({round(ratio * 100)}% coverage, within pages crawled)"
            ),
            detail={
                "locale": locale, "locale_page_count": len(group), "primary_page_count": len(primary),
                "coverage_ratio": round(ratio, 3),
                "locale_urls": sorted(p.url for p in group),
                "note": "Limited to pages found within this crawl's max_pages cap, not necessarily the whole site.",
            },
        ))

    return findings
