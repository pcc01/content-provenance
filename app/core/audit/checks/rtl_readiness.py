"""
Phase 11 — RTL/logical-CSS-properties readiness. New capability, no
existing script to port: static analysis of a page's stylesheet + inline
style text, counting physical CSS properties (margin-left, text-align:
left, float: right, ...) against their logical/writing-mode-aware
equivalents (margin-inline-start, text-align: start, ...). Heavy physical
usage with no logical usage and no `[dir=]`/`:dir()` CSS is a heuristic
signal a page's layout won't adapt cleanly to an RTL locale — not a
compliance certification, just "worth a human look."
"""

import re
from typing import Dict, List

from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_PHYSICAL_PATTERNS = {
    "margin-left": re.compile(r"\bmargin-left\b"),
    "margin-right": re.compile(r"\bmargin-right\b"),
    "padding-left": re.compile(r"\bpadding-left\b"),
    "padding-right": re.compile(r"\bpadding-right\b"),
    "border-left": re.compile(r"\bborder-left\b"),
    "border-right": re.compile(r"\bborder-right\b"),
    "left:": re.compile(r"(?<![-\w])left\s*:"),
    "right:": re.compile(r"(?<![-\w])right\s*:"),
    "float: left/right": re.compile(r"\bfloat\s*:\s*(left|right)\b"),
    "text-align: left/right": re.compile(r"\btext-align\s*:\s*(left|right)\b"),
}

_LOGICAL_PATTERNS = {
    "margin-inline-start/end": re.compile(r"\bmargin-inline-(start|end)\b"),
    "padding-inline-start/end": re.compile(r"\bpadding-inline-(start|end)\b"),
    "border-inline-start/end": re.compile(r"\bborder-inline-(start|end)\b"),
    "inset-inline-start/end": re.compile(r"\binset-inline-(start|end)\b"),
    "text-align: start/end": re.compile(r"\btext-align\s*:\s*(start|end)\b"),
}

_DIR_SUPPORT_RE = re.compile(r"\[dir\s*=|:dir\(")

# Below this many physical-property hits, a page isn't worth flagging —
# a handful of incidental left/right usages is normal even on RTL-ready
# sites (e.g. a single decorative icon offset).
_MIN_PHYSICAL_HITS_TO_FLAG = 5


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        css_texts = list(page.stylesheet_texts.values())
        if not css_texts:
            continue
        combined = "\n".join(css_texts)

        physical_counts = {name: len(pat.findall(combined)) for name, pat in _PHYSICAL_PATTERNS.items()}
        logical_counts = {name: len(pat.findall(combined)) for name, pat in _LOGICAL_PATTERNS.items()}
        total_physical = sum(physical_counts.values())
        total_logical = sum(logical_counts.values())
        has_dir_support = bool(_DIR_SUPPORT_RE.search(combined))

        if total_physical < _MIN_PHYSICAL_HITS_TO_FLAG or total_logical > 0 or has_dir_support:
            continue

        examples = [name for name, count in physical_counts.items() if count > 0][:5]
        findings.append(SiteAuditFinding(
            audit_id=audit.id, page_id=page_ids.get(page.url), check=SiteAuditCheck.RTL_READINESS,
            finding_type="rtl_risk_physical_properties", severity=SiteAuditSeverity.WARNING,
            summary=f"{total_physical} physical CSS properties found, no logical-property or dir-aware CSS detected",
            detail={
                "url": page.url, "physical_property_count": total_physical,
                "example_properties": examples, "stylesheets_checked": len(css_texts),
            },
        ))

    return findings
