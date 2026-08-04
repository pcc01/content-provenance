"""
Phase 11 — mixed-locale detection. Redesigned, DB-backed version of what
website_language_reviewer.py / website_language_analyzer.py did as
standalone scripts: flag pages whose detected content language doesn't
match their expected locale, pages mixing multiple languages, internal
links pointing to an unexpectedly different-language page, and notable
external embeds (YouTube) with a mismatched `hl` locale param.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from langdetect import detect, LangDetectException

from app.core.audit.crawler import CrawledPage
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditSeverity

# Same locale-in-path convention the original analyzer script used, e.g.
# /es/, /fr-FR/ — kept as a compact code list rather than a full BCP-47
# validator, which would be overkill for "does this URL suggest a locale."
_LANG_CODES = [
    "aa", "ab", "ae", "af", "ak", "am", "an", "ar", "as", "av", "ay", "az", "ba", "be", "bg", "bh", "bi", "bm",
    "bn", "bo", "br", "bs", "ca", "ce", "ch", "co", "cr", "cs", "cu", "cv", "cy", "da", "de", "dv", "dz", "ee",
    "el", "en", "eo", "es", "et", "eu", "fa", "ff", "fi", "fj", "fo", "fr", "fy", "ga", "gd", "gl", "gn", "gu",
    "gv", "ha", "he", "hi", "ho", "hr", "ht", "hu", "hy", "hz", "ia", "id", "ie", "ig", "ii", "ik", "io", "is",
    "it", "iu", "ja", "jv", "ka", "kg", "ki", "kj", "kk", "kl", "km", "kn", "ko", "kr", "ks", "ku", "kv", "kw",
    "ky", "la", "lb", "lg", "li", "ln", "lo", "lt", "lu", "lv", "mg", "mh", "mi", "mk", "ml", "mn", "mr", "ms",
    "mt", "my", "na", "nb", "nd", "ne", "ng", "nl", "nn", "no", "nr", "nv", "ny", "oc", "oj", "om", "or", "os",
    "pa", "pi", "pl", "ps", "pt", "qu", "rm", "rn", "ro", "ru", "rw", "sa", "sc", "sd", "se", "sg", "si", "sk",
    "sl", "sm", "sn", "so", "sq", "sr", "ss", "st", "su", "sv", "sw", "ta", "te", "tg", "th", "ti", "tk", "tl",
    "tn", "to", "tr", "ts", "tt", "tw", "ty", "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "wo", "xh", "yi",
    "yo", "za", "zh", "zu",
]
_LOCALE_PATH_RE = re.compile(r"/(" + "|".join(_LANG_CODES) + r"|[a-z]{2}-[a-zA-Z]{2})/")


def _locale_tag_from_path(path: str) -> Optional[str]:
    """Like _locale_from_path but keeps a region subtag if the URL has one
    (e.g. "/en-gb/" -> "en-gb"), for the region-aware checks (cookie_consent,
    locale_format) that need to distinguish e.g. US from other English-
    speaking markets rather than just "English."""
    match = _LOCALE_PATH_RE.search(path)
    return match.group(1).lower() if match else None


def _locale_from_path(path: str) -> Optional[str]:
    tag = _locale_tag_from_path(path)
    return tag.split("-")[0] if tag else None


def _page_region_tag(page_url: str, html_lang: Optional[str]) -> Optional[str]:
    """Best-guess full locale tag for a page, shared by the region-aware
    checks: a URL path locale (e.g. "/en-gb/") is a more deliberate signal
    of which market a page targets than a possibly-templated <html lang>,
    so it takes priority when both are present."""
    tag = _locale_tag_from_path(urlparse(page_url).path)
    return tag or (html_lang.lower() if html_lang else None)


def _detect(text: str) -> Optional[str]:
    text = text.strip()
    if len(text) < 20:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def _primary(code: Optional[str]) -> Optional[str]:
    return code.split("-")[0].lower() if code else None


def run(pages: List[CrawledPage], page_ids: Dict[str, str], audit: SiteAudit) -> List[SiteAuditFinding]:
    findings: List[SiteAuditFinding] = []
    expected_primary = _primary(audit.primary_language)

    lang_by_url: Dict[str, Optional[str]] = {}
    expected_by_url: Dict[str, Optional[str]] = {}
    for page in pages:
        joined = " ".join(page.text_blocks)[:5000]
        lang_by_url[page.url] = _detect(joined)
        expected_by_url[page.url] = _locale_from_path(urlparse(page.url).path) or expected_primary

    for page in pages:
        page_lang = lang_by_url[page.url]
        expected = expected_by_url[page.url]
        page_id = page_ids.get(page.url)
        snippet = " ".join(" ".join(page.text_blocks).split()[:50])

        # 1. Page-language mismatch.
        if page_lang and expected and page_lang != _primary(expected):
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.MIXED_LOCALE,
                finding_type="page_language_mismatch", severity=SiteAuditSeverity.WARNING,
                summary=f"Expected {expected.upper()} content but detected {page_lang.upper()}",
                detail={"url": page.url, "expected": expected, "detected": page_lang, "snippet": snippet},
            ))

        # 2. Multi-language page — individual text blocks disagree with the
        # page's own dominant detected language.
        block_langs = {_detect(b) for b in page.text_blocks}
        block_langs.discard(None)
        other_langs = block_langs - ({page_lang} if page_lang else set())
        if other_langs:
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.MIXED_LOCALE,
                finding_type="multi_language_page", severity=SiteAuditSeverity.INFO,
                summary=f"Page mixes languages: primary {(page_lang or 'unknown').upper()}, also found {sorted(l.upper() for l in other_langs)}",
                detail={"url": page.url, "primary_language": page_lang, "other_languages": sorted(other_langs)},
            ))

        # 3. Internal links to an already-crawled page whose detected
        # language differs from what this page's link context would expect.
        for link in page.links:
            target_lang = lang_by_url.get(link.href)
            if target_lang is None or page_lang is None or target_lang == page_lang:
                continue
            findings.append(SiteAuditFinding(
                audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.MIXED_LOCALE,
                finding_type="cross_language_link", severity=SiteAuditSeverity.INFO,
                summary=f"{(page_lang or '?').upper()} page links to {target_lang.upper()} content",
                detail={"from_url": page.url, "from_lang": page_lang, "to_url": link.href, "to_lang": target_lang},
            ))

        # 4. External YouTube embeds/links with a reportable hl= locale.
        embed_urls = list(page.iframe_urls) + [l.href for l in page.links]
        for embed_url in embed_urls:
            parsed = urlparse(embed_url)
            if "youtube.com" not in parsed.netloc and "youtu.be" not in parsed.netloc:
                continue
            hl = parse_qs(parsed.query).get("hl", [None])[0]
            if not hl:
                continue
            hl_primary = _primary(hl)
            if expected_primary and hl_primary and hl_primary != expected_primary:
                findings.append(SiteAuditFinding(
                    audit_id=audit.id, page_id=page_id, check=SiteAuditCheck.MIXED_LOCALE,
                    finding_type="external_embed_mismatch", severity=SiteAuditSeverity.INFO,
                    summary=f"Embedded/linked YouTube content locale ({hl}) doesn't match site's primary language",
                    detail={"from_url": page.url, "embed_url": embed_url, "embed_locale": hl},
                ))

    return findings
