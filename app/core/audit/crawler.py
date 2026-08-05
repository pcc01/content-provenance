"""
Phase 11 — site crawler for the i18n/l10n/compliance audit toolkit.

Distinct from app/core/page_fetch.py's fetch_and_render: that fetches ONE
url this system is reviewing ITS OWN translations against. This crawls
MANY pages of a THIRD-PARTY site, collecting raw material (text blocks,
links, stylesheet/script bodies) for the check modules in
app/core/audit/checks/ to inspect — no TranslationUnits, no harvesting, no
data-tu-id tagging. Reuses Playwright (already a dependency) rather than
requests+BeautifulSoup so client-rendered SPA content is seen, and reuses
page_fetch.py's robots.txt check rather than duplicating it.
"""

import asyncio
from dataclasses import dataclass, field
from collections import deque
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from app.core.page_fetch import PageFetchError, _check_robots_allowed

# Politeness delay between page loads — the scripts this replaces had none.
_CRAWL_DELAY_SECONDS = 0.3
_PAGE_LOAD_TIMEOUT_MS = 30000
_NETWORK_IDLE_TIMEOUT_MS = 8000

# Same tag list the original scripts used for "meaningful" text content.
_TEXT_TAGS = ["p", "h1", "h2", "h3", "li", "span", "div"]

_EXTRACT_JS = """
() => {
  const textTags = %s;
  const textBlocks = [];
  for (const tag of textTags) {
    for (const el of document.querySelectorAll(tag)) {
      const text = (el.innerText || el.textContent || '').trim();
      if (text.length > 20) textBlocks.push(text);
    }
  }
  const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
    href: a.href, text: (a.textContent || '').trim(),
  }));
  const stylesheetUrls = Array.from(document.querySelectorAll('link[rel="stylesheet"][href]')).map(l => l.href);
  const inlineStyles = Array.from(document.querySelectorAll('style')).map(s => s.textContent || '');
  const scriptUrls = Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
  const inlineScripts = Array.from(document.querySelectorAll('script:not([src])')).map(s => s.textContent || '');
  const iframeUrls = Array.from(document.querySelectorAll('iframe[src]')).map(f => f.src);
  const hreflangLinks = Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]')).map(l => ({
    hreflang: l.getAttribute('hreflang') || '', href: l.href,
  }));
  const formInputs = Array.from(document.querySelectorAll('input')).map(i => ({
    name: i.name || i.id || '', type: i.type || 'text',
    pattern: i.getAttribute('pattern') || '', maxlength: i.getAttribute('maxlength') || '',
  }));
  const selects = Array.from(document.querySelectorAll('select')).map(s => ({
    name: s.name || s.id || '',
    options: Array.from(s.options).map(o => (o.textContent || '').trim()).filter(Boolean),
  }));
  const descMeta = document.querySelector('meta[name="description"]');
  const ogLocaleMeta = document.querySelector('meta[property="og:locale"]');
  return {
    htmlLang: document.documentElement.getAttribute('lang'),
    htmlDir: document.documentElement.getAttribute('dir'),
    title: document.title || '',
    metaDescription: descMeta ? (descMeta.content || '').trim() : '',
    ogLocale: ogLocaleMeta ? (ogLocaleMeta.content || '').trim() : '',
    textBlocks, links, stylesheetUrls, inlineStyles, scriptUrls, inlineScripts, iframeUrls,
    hreflangLinks, formInputs, selects,
  };
}
""" % (_TEXT_TAGS)


@dataclass
class CrawledLink:
    href: str
    text: str


# Cap how many linked stylesheets/scripts get their bodies fetched per page
# — pages can reference dozens of third-party scripts; the checks only need
# enough signal to flag a pattern, not exhaustive coverage.
_MAX_RESOURCES_PER_PAGE = 12
_MAX_RESOURCE_BYTES = 2_000_000


@dataclass
class CrawledPage:
    url: str
    status_code: Optional[int]
    html_lang: Optional[str]
    # <html dir="...">, for rtl_readiness's hard pass/fail check — distinct
    # from that module's existing CSS-heuristic signal.
    html_dir: Optional[str] = None
    # <title> and <meta name="description">/<meta property="og:locale">,
    # for seo_metadata — none of this was collected before that check needed it.
    title: str = ""
    meta_description: str = ""
    og_locale: Optional[str] = None
    text_blocks: List[str] = field(default_factory=list)
    links: List[CrawledLink] = field(default_factory=list)
    iframe_urls: List[str] = field(default_factory=list)
    # url -> body text, for the rtl_readiness/icu_i18n checks. Inline
    # style/script bodies use the page's own url as a synthetic key.
    stylesheet_texts: dict = field(default_factory=dict)
    script_texts: dict = field(default_factory=dict)
    # [{"hreflang": "en-GB", "href": "..."}], for the hreflang check.
    hreflang_links: List[dict] = field(default_factory=list)
    # [{"name": ..., "type": ..., "pattern": ..., "maxlength": ...}], for
    # the locale_format check's US-centric form-validation detection.
    form_inputs: List[dict] = field(default_factory=list)
    # [{"name": ..., "options": [...]}], same purpose (state/province dropdowns).
    selects: List[dict] = field(default_factory=list)


def _same_site(url: str, root_netloc: str) -> bool:
    """Matches the original scripts' domain check (substring of netloc) —
    permissive enough to follow subdomains without a heavier public-suffix
    lookup."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and root_netloc in parsed.netloc


def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


async def crawl_site(root_url: str, max_pages: int = 40) -> List[CrawledPage]:
    """BFS same-domain(+subdomain) crawl starting at root_url. Individual
    unreachable/disallowed pages are skipped, not fatal — only a failure to
    load the ROOT page aborts the whole crawl (nothing to report on
    otherwise)."""
    if not root_url.startswith(("http://", "https://")):
        raise PageFetchError("Only http:// and https:// URLs are supported.", status_code=400)

    root_netloc = urlparse(root_url).netloc
    queue = deque([root_url])
    visited: set = set()
    pages: List[CrawledPage] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            while queue and len(pages) < max_pages:
                url = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)

                if not await _check_robots_allowed(url):
                    continue

                crawled = await _crawl_one_page(browser, url)
                if crawled is None:
                    if url == root_url:
                        raise PageFetchError(f"Could not load {root_url}.", status_code=502)
                    continue

                pages.append(crawled)

                for link in crawled.links:
                    if not _same_site(link.href, root_netloc):
                        continue
                    clean = _clean_url(link.href)
                    if clean not in visited and clean not in queue:
                        queue.append(clean)

                await asyncio.sleep(_CRAWL_DELAY_SECONDS)
        finally:
            await browser.close()

    return pages


async def _fetch_resource_text(context, url: str) -> Optional[str]:
    """Fetches a linked CSS/JS resource's raw text via the SAME browser
    context the crawl used (cookies/session carry over, no separate HTTP
    client needed). Returns None on any failure — a missing stylesheet/
    script shouldn't abort a page's crawl, just skip that one resource."""
    try:
        response = await context.request.get(url, timeout=10000)
        if not response.ok:
            return None
        body = await response.body()
        if len(body) > _MAX_RESOURCE_BYTES:
            body = body[:_MAX_RESOURCE_BYTES]
        return body.decode("utf-8", errors="replace")
    except Exception:
        return None


async def _crawl_one_page(browser, url: str) -> Optional[CrawledPage]:
    page = await browser.new_page()
    try:
        try:
            response = await page.goto(url, wait_until="load", timeout=_PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            return None
        try:
            await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
        except Exception:
            pass  # some pages never go idle (polling/websockets) — proceed with what's loaded

        data = await page.evaluate(_EXTRACT_JS)

        stylesheet_texts = {}
        for css_url in data.get("stylesheetUrls", [])[:_MAX_RESOURCES_PER_PAGE]:
            text = await _fetch_resource_text(page.context, css_url)
            if text:
                stylesheet_texts[css_url] = text
        for i, inline in enumerate(data.get("inlineStyles", [])):
            if inline.strip():
                stylesheet_texts[f"{url}#inline-style-{i}"] = inline

        script_texts = {}
        for js_url in data.get("scriptUrls", [])[:_MAX_RESOURCES_PER_PAGE]:
            text = await _fetch_resource_text(page.context, js_url)
            if text:
                script_texts[js_url] = text
        for i, inline in enumerate(data.get("inlineScripts", [])):
            if inline.strip():
                script_texts[f"{url}#inline-script-{i}"] = inline

        return CrawledPage(
            url=url,
            status_code=response.status if response else None,
            html_lang=data.get("htmlLang"),
            html_dir=data.get("htmlDir"),
            title=data.get("title", ""),
            meta_description=data.get("metaDescription", ""),
            og_locale=data.get("ogLocale") or None,
            text_blocks=data.get("textBlocks", []),
            links=[
                CrawledLink(href=link["href"], text=link["text"])
                for link in data.get("links", []) if link.get("href")
            ],
            iframe_urls=data.get("iframeUrls", []),
            stylesheet_texts=stylesheet_texts,
            script_texts=script_texts,
            hreflang_links=data.get("hreflangLinks", []),
            form_inputs=data.get("formInputs", []),
            selects=data.get("selects", []),
        )
    finally:
        await page.close()
