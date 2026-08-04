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
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_FIXED_WIDTH_RE = re.compile(r"\b(?:width|max-width)\s*:\s*\d+(?:\.\d+)?(?:px|pt)\b")
_TRUNCATION_RE = re.compile(r"\boverflow(?:-x)?\s*:\s*hidden\b|\btext-overflow\s*:\s*ellipsis\b")

_MIN_RISKY_SELECTORS_TO_FLAG = 2


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        css_texts = list(page.stylesheet_texts.values())
        if not css_texts:
            continue
        combined = "\n".join(css_texts)

        risky_selectors = []
        for selector, body in _BLOCK_RE.findall(combined):
            if _FIXED_WIDTH_RE.search(body) and _TRUNCATION_RE.search(body):
                risky_selectors.append(selector.strip()[:80])

        if len(risky_selectors) < _MIN_RISKY_SELECTORS_TO_FLAG:
            continue

        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=page_ids.get(page.url), check=SiteAuditCheck.TEXT_EXPANSION,
            finding_type="text_expansion_risk", severity=SiteAuditSeverity.WARNING,
            summary=f"{len(risky_selectors)} CSS rule(s) combine a fixed width with clipped/hidden overflow — translated text may be cut off",
            detail={"url": page.url, "example_selectors": risky_selectors[:5], "count": len(risky_selectors)},
        ))

    return findings
