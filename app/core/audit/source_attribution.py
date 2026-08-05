"""
Attributes a stylesheet/script URL to a human-readable source, for checks
that read page.stylesheet_texts/script_texts and previously just reported
"N properties found" across a page with no indication of WHOSE code is
responsible — not actionable for a site owner who doesn't know if the
fix is theirs to make. Two tiers, always both computed: a generic
`category` that works on any site regardless of platform, and an optional
`platform_detail` — currently WordPress-only, using the same
/wp-content/themes//wp-content/plugins//wp-includes/ path convention
crawler.py's _VENDOR_CSS_URL_RE already relies on to EXCLUDE vendor CSS,
now surfaced as information instead of just a filter. On a non-WordPress
site platform_detail is simply None — category alone is still useful
(same_origin vs third_party vs inline), just less specific.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

_WP_THEME_RE = re.compile(r"/wp-content/themes/([^/]+)/")
_WP_PLUGIN_RE = re.compile(r"/wp-content/plugins/([^/]+)/")
_WP_CORE_RE = re.compile(r"/wp-includes/")


@dataclass
class SourceAttribution:
    category: str  # "inline" | "same_origin" | "third_party"
    platform_detail: Optional[str] = None  # e.g. "WordPress theme: customizr"

    def as_dict(self) -> dict:
        d = {"category": self.category}
        if self.platform_detail:
            d["platform_detail"] = self.platform_detail
        return d


def attribute_source(resource_url: str, page_url: str) -> SourceAttribution:
    """resource_url is either a real stylesheet/script URL, or one of
    crawler.py's synthetic inline keys (f"{page_url}#inline-style-{i}")."""
    if "#inline-style-" in resource_url or "#inline-script-" in resource_url:
        return SourceAttribution(category="inline")

    theme_match = _WP_THEME_RE.search(resource_url)
    if theme_match:
        return SourceAttribution(category="same_origin", platform_detail=f"WordPress theme: {theme_match.group(1)}")
    plugin_match = _WP_PLUGIN_RE.search(resource_url)
    if plugin_match:
        return SourceAttribution(category="same_origin", platform_detail=f"WordPress plugin: {plugin_match.group(1)}")
    if _WP_CORE_RE.search(resource_url):
        return SourceAttribution(category="same_origin", platform_detail="WordPress core")

    page_netloc = urlparse(page_url).netloc
    resource_netloc = urlparse(resource_url).netloc
    if resource_netloc and resource_netloc != page_netloc:
        return SourceAttribution(category="third_party")
    return SourceAttribution(category="same_origin")
