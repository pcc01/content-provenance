"""
Locale-switcher integrity. New capability: even a fully translated site is
a bad experience if clicking the language toggle dumps a visitor onto the
other locale's homepage instead of the equivalent page they were just
reading. Detects candidate switcher links by their visible text (a
language name or bare language code) and, for links whose target is also
in the crawled set, compares the URL path with each locale prefix
stripped — if they don't match, the switcher isn't actually equivalent.

A companion, lower-confidence finding flags pages that have NO candidate
switcher link at all despite the site clearly being multi-locale — no
path-comparison involved, just "a visitor here has no way to change
language without editing the URL by hand."
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.core.audit.checks.mixed_locale import _LANG_CODES, _LOCALE_PATH_RE, _locale_from_path
from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

# Substring match against link text — safe for full autonyms/English names
# (low collision risk), unlike bare 2-letter codes which need an exact
# match (see _looks_like_switcher_link) to avoid matching incidental text.
_LANGUAGE_NAMES = [
    "english", "français", "francais", "french", "deutsch", "german", "español", "espanol",
    "spanish", "italiano", "italian", "português", "portugues", "portuguese", "中文", "日本語",
    "한국어", "العربية", "arabic", "русский", "russian", "nederlands", "dutch", "svenska",
    "swedish", "polski", "polish", "türkçe", "turkce", "turkish", "עברית", "hebrew",
]
_LANG_CODE_SET = set(_LANG_CODES)


def _looks_like_switcher_link(text: str) -> bool:
    text = text.strip().lower()
    if not text:
        return False
    if any(name in text for name in _LANGUAGE_NAMES):
        return True
    # Bare code ("FR", "en-GB") or "FR |" / "( FR )" style — strip common
    # separators before the exact-match check so real switcher UIs (which
    # often render as "EN | FR | DE") still count without loosening the
    # exact-match enough to catch arbitrary two-letter words.
    bare = re.sub(r"[|/,()\[\]]", "", text).strip()
    primary = bare.split("-")[0]
    return bare in _LANG_CODE_SET or primary in _LANG_CODE_SET


def _strip_locale_prefix(path: str) -> str:
    stripped = _LOCALE_PATH_RE.sub("/", path)
    return stripped if stripped.startswith("/") else f"/{stripped}"


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []

    pages_by_url = {p.url: p for p in pages}
    locales_seen = {_locale_from_path(urlparse(p.url).path) for p in pages} - {None}
    site_is_multi_locale = len(locales_seen) > 1
    if not site_is_multi_locale:
        return findings

    for page in pages:
        page_id = page_ids.get(page.url)
        source_stripped = _strip_locale_prefix(urlparse(page.url).path)

        switcher_links = [link for link in page.links if _looks_like_switcher_link(link.text)]

        if not switcher_links:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_SWITCHER,
                finding_type="no_locale_switcher_detected", severity=SiteAuditSeverity.INFO,
                summary="No language-switcher link detected on this page, though the site has multiple locales",
                detail={"url": page.url},
            ))
            continue

        for link in switcher_links:
            target = pages_by_url.get(link.href)
            if target is None:
                continue  # target not in this crawl — can't verify equivalence
            target_stripped = _strip_locale_prefix(urlparse(target.url).path)
            if target_stripped == source_stripped:
                continue
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.LOCALE_SWITCHER,
                finding_type="locale_switcher_loses_place", severity=SiteAuditSeverity.WARNING,
                summary=f"Language switcher (\"{link.text.strip()}\") lands on a different page instead of this page's translation",
                detail={
                    "from_url": page.url, "to_url": target.url, "link_text": link.text.strip(),
                    "from_path": source_stripped, "to_path": target_stripped,
                },
            ))

    return findings
