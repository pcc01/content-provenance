"""
Phase 11 — privacy-policy review. Extends privacy_policy_scraper.py's
keyword-link-finding idea with a genuinely new check: does the linked
privacy/legal content match the LANGUAGE of the page linking to it (e.g. a
French page linking to an English-only privacy policy) — a real
localization-compliance gap the original script never checked, since it
only dumped text to a file rather than analyzing it.
"""

import re
from typing import Dict, List

from langdetect import detect, LangDetectException

from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_KEYWORDS = ["privacy", "cookie", "gdpr", "ccpa", "data protection", "legal", "terms"]
_KEYWORD_RE = re.compile("|".join(re.escape(k) for k in _KEYWORDS), re.IGNORECASE)


def _detect(text: str) -> str:
    text = text.strip()
    if len(text) < 20:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    lang_by_url = {p.url: _detect(" ".join(p.text_blocks)[:5000]) for p in pages}
    pages_by_url = {p.url: p for p in pages}

    for page in pages:
        page_id = page_ids.get(page.url)
        page_lang = lang_by_url.get(page.url)

        privacy_links = sorted({
            link.href for link in page.links if _KEYWORD_RE.search(link.text)
        })
        if not privacy_links:
            continue

        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PRIVACY,
            finding_type="privacy_link_found", severity=SiteAuditSeverity.INFO,
            summary=f"{len(privacy_links)} privacy/legal-labeled link(s) found",
            detail={"url": page.url, "privacy_links": privacy_links},
        ))

        for privacy_url in privacy_links:
            target = pages_by_url.get(privacy_url)
            if target is None:
                continue  # not part of this crawl (off-domain or beyond max_pages) — nothing to compare
            target_lang = lang_by_url.get(privacy_url)
            if page_lang and target_lang and page_lang != target_lang:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PRIVACY,
                    finding_type="privacy_language_mismatch", severity=SiteAuditSeverity.WARNING,
                    summary=f"Page is {page_lang.upper()} but its privacy policy is {target_lang.upper()}",
                    detail={
                        "from_url": page.url, "from_lang": page_lang,
                        "privacy_url": privacy_url, "privacy_lang": target_lang,
                    },
                ))

    return findings
