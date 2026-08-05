"""
SEO metadata parity. New capability: a page that's otherwise fully
translated but still ships an English <meta name="description"> (or an
og:locale tag naming the wrong locale) is a frequent, cheap-to-miss gap —
search engines index the metadata a visitor never sees directly, so it
can go unnoticed indefinitely. Deliberately skips <title> — langdetect
needs a reasonable amount of text to be reliable and titles are usually
under 20 characters, exactly the threshold mixed_locale._detect already
enforces to avoid noisy false positives on short strings.
"""

from typing import Dict, List
from urllib.parse import urlparse

from app.core.audit.checks.mixed_locale import _detect, _locale_from_path, _primary
from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []
    audit_primary = audit.primary_language.split("-")[0].lower()

    for page in pages:
        expected = _locale_from_path(urlparse(page.url).path)
        if expected is None or expected == audit_primary:
            continue  # only meaningful for pages deliberately targeting a non-primary locale
        page_id = page_ids.get(page.url)

        if not page.meta_description.strip():
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.SEO_METADATA,
                finding_type="seo_description_missing", severity=SiteAuditSeverity.INFO,
                summary=f"No meta description found on a page targeting {expected.upper()}",
                detail={"url": page.url, "expected_locale": expected},
            ))
        else:
            detected = _detect(page.meta_description)
            if detected and detected != expected:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.SEO_METADATA,
                    finding_type="seo_description_not_localized", severity=SiteAuditSeverity.WARNING,
                    summary=f"Meta description is {detected.upper()} but this page targets {expected.upper()}",
                    detail={
                        "url": page.url, "expected_locale": expected, "detected_language": detected,
                        "description": page.meta_description,
                    },
                ))

        if page.og_locale:
            og_primary = _primary(page.og_locale.replace("_", "-"))
            if og_primary and og_primary != expected:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.SEO_METADATA,
                    finding_type="og_locale_mismatch", severity=SiteAuditSeverity.INFO,
                    summary=f"og:locale is \"{page.og_locale}\" but this page targets {expected.upper()}",
                    detail={"url": page.url, "expected_locale": expected, "og_locale": page.og_locale},
                ))

    return findings
