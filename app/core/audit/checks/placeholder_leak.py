"""
Phase 12 — untranslated placeholder leakage. New capability, a broader
version of icu_i18n.py's ICU-syntax check: template placeholders
({{variable}}, %s, {0}) or literal TODO/Lorem-ipsum filler text that
survived into what a visitor actually sees is a real, visible bug — the
kind of thing that's obvious once pointed out but easy to miss in a
translation review that only reads target text out of context.
"""

import re
from typing import Dict, List

from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

_PATTERNS = {
    "double_curly_placeholder": re.compile(r"\{\{\s*[\w.]+\s*\}\}"),
    "printf_placeholder": re.compile(r"%\(\w+\)s|%s\b"),
    "numbered_brace_placeholder": re.compile(r"\{\d+\}"),
    "lorem_ipsum": re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    "todo_marker": re.compile(r"\b(TODO|FIXME|TRANSLATE_?ME)\b"),
}


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    for page in pages:
        page_id = page_ids.get(page.url)
        # One finding per page is enough to flag it for review — matches
        # icu_i18n.py's icu_syntax_leak convention (stop at first match).
        for block in page.text_blocks:
            match = next((name for name, pat in _PATTERNS.items() if pat.search(block)), None)
            if match is None:
                continue
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.PLACEHOLDER_LEAK,
                finding_type="placeholder_leak", severity=SiteAuditSeverity.WARNING,
                summary=f"Possible untranslated placeholder/filler text ({match.replace('_', ' ')})",
                detail={"url": page.url, "pattern": match, "snippet": block[:200]},
            ))
            break

    return findings
