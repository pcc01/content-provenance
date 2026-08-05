"""
Phase 12 — text expansion / truncation risk. New capability: German,
Finnish, Russian, etc. commonly run 20-35% longer than the equivalent
English string. A CSS rule combining a fixed width with `overflow:hidden`
or `text-overflow:ellipsis` is a strong signal that translated text will
be visually clipped — a real, common expansion-blocker, not a hypothetical.
"""

import re
from typing import Dict, List

from app.core.audit.crawler import CrawledPage
from app.core.audit.source_attribution import attribute_source
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_FIXED_WIDTH_RE = re.compile(r"\b(?:width|max-width)\s*:\s*\d+(?:\.\d+)?(?:px|pt)\b")
_TRUNCATION_RE = re.compile(r"\boverflow(?:-x)?\s*:\s*hidden\b|\btext-overflow\s*:\s*ellipsis\b")

_MIN_RISKY_SELECTORS_TO_FLAG = 2


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        if not page.stylesheet_texts:
            continue

        risky_selectors: List[str] = []
        # Per-source, not combined — a site owner needs to know WHOSE code
        # is responsible before "fix this" is actionable advice.
        counts_by_source: Dict[str, int] = {}
        for source_url, css_text in page.stylesheet_texts.items():
            for selector, body in _BLOCK_RE.findall(css_text):
                if _FIXED_WIDTH_RE.search(body) and _TRUNCATION_RE.search(body):
                    risky_selectors.append(selector.strip()[:80])
                    counts_by_source[source_url] = counts_by_source.get(source_url, 0) + 1

        if len(risky_selectors) < _MIN_RISKY_SELECTORS_TO_FLAG:
            continue

        sources = [
            {"url": url, "count": count, **attribute_source(url, page.url).as_dict()}
            for url, count in sorted(counts_by_source.items(), key=lambda kv: -kv[1])
        ]

        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=page_ids.get(page.url), check=SiteAuditCheck.TEXT_EXPANSION,
            finding_type="text_expansion_risk", severity=SiteAuditSeverity.WARNING,
            summary=f"{len(risky_selectors)} CSS rule(s) combine a fixed width with clipped/hidden overflow — translated text may be cut off",
            detail={
                "url": page.url, "example_selectors": risky_selectors[:5], "count": len(risky_selectors),
                "sources": sources[:5],
            },
        ))

    return findings
