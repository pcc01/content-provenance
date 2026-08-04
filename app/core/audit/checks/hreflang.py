"""
Phase 12 — hreflang / canonical correctness. New capability, a significant
SEO gap for multi-market sites: missing or non-reciprocal `hreflang`
annotations mean search engines can serve the wrong locale to the wrong
searchers. Only reasons about pages actually in the crawled set — a
target outside max_pages/off-domain can't be checked for reciprocity, so
that case is silently skipped rather than false-flagged.
"""

from typing import Dict, List
from urllib.parse import urlparse

from app.core.audit.checks.mixed_locale import _locale_from_path
from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    pages_by_url = {p.url: p for p in pages}
    site_is_multi_locale = len({
        _locale_from_path(urlparse(p.url).path) for p in pages
    } - {None}) > 1

    for page in pages:
        page_id = page_ids.get(page.url)

        if not page.hreflang_links:
            if site_is_multi_locale:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.HREFLANG,
                    finding_type="missing_hreflang_annotations", severity=SiteAuditSeverity.INFO,
                    summary="Site has multiple locale paths, but this page declares no hreflang alternates",
                    detail={"url": page.url},
                ))
            continue

        codes = [l.get("hreflang", "").lower() for l in page.hreflang_links]
        if len(page.hreflang_links) > 1 and "x-default" not in codes:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.HREFLANG,
                finding_type="missing_x_default", severity=SiteAuditSeverity.INFO,
                summary=f"{len(page.hreflang_links)} hreflang alternates declared but no x-default fallback",
                detail={"url": page.url, "hreflang_codes": codes},
            ))

        for link in page.hreflang_links:
            target_url = link.get("href")
            target = pages_by_url.get(target_url)
            if target is None:
                continue  # not in this crawl — can't verify reciprocity
            target_back_hrefs = {l.get("href") for l in target.hreflang_links}
            if page.url not in target_back_hrefs:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.HREFLANG,
                    finding_type="hreflang_not_reciprocal", severity=SiteAuditSeverity.WARNING,
                    summary=f"Page links to {target_url} via hreflang, but that page doesn't link back",
                    detail={"from_url": page.url, "to_url": target_url, "hreflang": link.get("hreflang")},
                ))

    return findings
