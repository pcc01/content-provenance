"""Fetch a web page's readable text for the Translate Workbench's "from URL"
source — one block per <p>/<h1..4>/<li>/<blockquote>, in document order.

Uses the same headless Chromium as app/core/page_fetch.py (so JS-rendered
pages are seen), and reuses its scheme + robots.txt guards. Deliberately
NOT SSRF-hardened against private/loopback ranges — same rationale as
page_fetch.py: the operator is translating content they control, including
localhost dev servers.
"""

from typing import List, Tuple
from urllib.parse import urlparse

from app.core.page_fetch import PageFetchError, _check_robots_allowed, _normalize

_LOAD_TIMEOUT_MS = 30000
_IDLE_TIMEOUT_MS = 8000
_MIN_BLOCK_CHARS = 25

# Text-bearing block tags, taken in document order. querySelectorAll returns
# each element once even when several selectors in the list match it, so a
# <p> inside <main> isn't double-counted.
_EXTRACT_JS = """
() => {
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('p, h1, h2, h3, h4, li, blockquote')) {
    const t = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    if (t.length < %d || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return { title: (document.title || '').trim(), blocks: out };
}
""" % _MIN_BLOCK_CHARS


def url_fetch_available() -> bool:
    try:
        import playwright.async_api  # noqa: F401
        return True
    except Exception:
        return False


async def fetch_url_blocks(url: str) -> Tuple[str, List[str]]:
    """(page title, [text block, ...]) for a URL. Raises PageFetchError with a
    meaningful status_code (400 bad scheme, 403 robots, 422 no text, 502
    fetch failure)."""
    if not url.startswith(("http://", "https://")):
        raise PageFetchError("Only http:// and https:// URLs are supported.", status_code=400)
    if not urlparse(url).netloc:
        raise PageFetchError("That doesn't look like a full URL.", status_code=400)
    if not await _check_robots_allowed(url):
        raise PageFetchError(f"{url} disallows fetching per its robots.txt.", status_code=403)

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await (await browser.new_context()).new_page()
                try:
                    await page.goto(url, wait_until="load", timeout=_LOAD_TIMEOUT_MS)
                except Exception as e:
                    raise PageFetchError(f"Could not load {url}: {e}", status_code=502) from e
                try:
                    await page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT_MS)
                except Exception:
                    pass  # polling/websocket pages never go idle — proceed with what loaded
                result = await page.evaluate(_EXTRACT_JS)
            finally:
                await browser.close()
    except PageFetchError:
        raise
    except Exception as e:
        raise PageFetchError(f"Failed to fetch {url}: {e}", status_code=502) from e

    blocks: List[str] = []
    seen = set()
    for raw in result.get("blocks", []):
        b = _normalize(raw)
        if b and b not in seen:
            seen.add(b)
            blocks.append(b)
    if not blocks:
        raise PageFetchError("No readable text found at that URL.", status_code=422)
    return (result.get("title") or url), blocks
