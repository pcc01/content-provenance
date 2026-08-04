"""
Phase 11/12 — privacy-policy review. Extends privacy_policy_scraper.py's
keyword-link-finding idea with two genuinely new checks: does the linked
privacy content match the LANGUAGE of the page linking to it (Phase 11 —
e.g. a French page linking to an English-only privacy policy), and, per
region (Phase 12), does the page carry the specific signals its applicable
regulation requires — a CCPA-style "Do Not Sell My Personal Information"
link, or a privacy policy that actually mentions the regulation it's
supposed to comply with — rather than a single generic "policy exists."
"""

import re
from typing import Dict, List

from langdetect import detect, LangDetectException

from app.core.audit.checks.mixed_locale import _page_region_tag
from app.core.audit.crawler import CrawledPage
from app.core.audit.regions import (
    jurisdictions_for_region, region_from_locale_tag, regulation_summaries_for_region,
    regulations_for_region, requires_opt_out_link,
)
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_KEYWORDS = ["privacy", "cookie", "gdpr", "ccpa", "data protection", "legal", "terms"]
_KEYWORD_RE = re.compile("|".join(re.escape(k) for k in _KEYWORDS), re.IGNORECASE)

_OPT_OUT_LINK_RE = re.compile(r"do not sell|do not share|your privacy choices|opt out of sale", re.IGNORECASE)

# Keyed by jurisdiction_id (unique per app/core/audit/data/jurisdictions/*.json
# file), NOT the "framework" field — aepd_ar.json and pdpa_singapore.json
# both carry framework="pdpa" in the source data, a real collision there.
_JURISDICTION_LANGUAGE_HINTS = {
    "gdpr_eu": re.compile(r"gdpr|general data protection regulation|right to erasure|data protection officer", re.IGNORECASE),
    "ccpa_california": re.compile(r"ccpa|cpra|california consumer privacy", re.IGNORECASE),
    "lgpd_brazil": re.compile(r"lgpd|lei geral de prote", re.IGNORECASE),
    "pipeda_canada": re.compile(r"pipeda|personal information protection", re.IGNORECASE),
    "pdpa_singapore": re.compile(r"pdpa|personal data protection act", re.IGNORECASE),
    "popia_za": re.compile(r"popia|protection of personal information", re.IGNORECASE),
    "privacy_act_au": re.compile(r"privacy act|australian privacy principles", re.IGNORECASE),
    "lpdc_mx": re.compile(r"aviso de privacidad|datos personales", re.IGNORECASE),
    "aepd_ar": re.compile(r"ley 25\.?326|aaip|datos personales", re.IGNORECASE),
}


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
        region = region_from_locale_tag(_page_region_tag(page.url, page.html_lang))
        applicable_regs = regulations_for_region(region)
        jurisdictions = jurisdictions_for_region(region)

        if applicable_regs:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PRIVACY,
                finding_type="applicable_regulations", severity=SiteAuditSeverity.INFO,
                summary=f"Likely applicable privacy regulation(s) for {region}: {', '.join(applicable_regs)}",
                detail={
                    "url": page.url, "region": region, "regulations": applicable_regs,
                    "summaries": regulation_summaries_for_region(region),
                },
            ))

        if requires_opt_out_link(region):
            has_opt_out = any(_OPT_OUT_LINK_RE.search(link.text) for link in page.links)
            if not has_opt_out:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PRIVACY,
                    finding_type="missing_ccpa_optout_link", severity=SiteAuditSeverity.WARNING,
                    summary=f"No \"Do Not Sell My Personal Information\" style link found on a page targeting {region}",
                    detail={"url": page.url, "region": region},
                ))

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

            target_text = " ".join(target.text_blocks) if target else ""
            for jurisdiction in jurisdictions:
                jid = jurisdiction.get("jurisdiction_id", "")
                hint = _JURISDICTION_LANGUAGE_HINTS.get(jid)
                reg_name = jurisdiction.get("jurisdiction_name") or jid
                if hint and target_text and not hint.search(target_text):
                    findings.append(SiteAuditFinding(
                        audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PRIVACY,
                        finding_type="privacy_policy_missing_regulation_language", severity=SiteAuditSeverity.INFO,
                        summary=f"Privacy policy doesn't appear to mention {reg_name}, which likely applies to {region}",
                        detail={"url": page.url, "privacy_url": privacy_url, "region": region, "regulation": reg_name},
                    ))

    return findings
