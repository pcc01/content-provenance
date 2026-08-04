"""
Phase 8 — non-cooperative page review: fetch an arbitrary URL with a
headless browser, harvest its translatable text into TranslationUnits
(matched by a stable hash so re-fetches reuse history instead of
duplicating/re-translating unchanged content), tag + rewrite a copy of the
DOM, and return it ready to serve same-origin. No site-specific
assumptions — works on any URL Playwright can render (server-rendered or
client-rendered SPA alike), not just apps we control.

Not SSRF-hardened against private IP ranges: this tool's whole point is
reviewing sites the operator runs themselves (including localhost dev
servers), so blocking private/loopback addresses would break the primary
use case. The one baseline guard kept is scheme restriction (http/https
only) to reject accidental file://, data:, etc. URLs. If this endpoint is
ever exposed to untrusted callers, revisit this.
"""

import asyncio
import hashlib
import re
import urllib.robotparser
from datetime import datetime
from typing import List
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.core.translation_backends import get_translation_backend
from app.models.schemas import PageSnapshot, TranslationMethod, TranslationStatus, TranslationUnit

_WHITESPACE_RE = re.compile(r"\s+")

_HARVEST_JS = r"""
() => {
  function isHarvestable(el) {
    if (!(el instanceof HTMLElement)) return false;
    const skip = ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'IFRAME', 'SVG'];
    if (skip.includes(el.tagName)) return false;
    if (el.children.length > 0) return false;
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (text.length < 2) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    return true;
  }
  function domPath(el) {
    const path = [];
    let node = el;
    while (node && node.nodeType === 1 && node.tagName !== 'HTML') {
      let selector = node.tagName;
      if (node.parentElement) {
        const siblings = Array.from(node.parentElement.children).filter((s) => s.tagName === node.tagName);
        if (siblings.length > 1) selector += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
      }
      path.unshift(selector);
      node = node.parentElement;
    }
    return path.join('>');
  }
  const results = [];
  let idx = 0;
  document.querySelectorAll('*').forEach((el) => {
    if (!isHarvestable(el)) return;
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    el.setAttribute('data-tu-harvest-idx', String(idx));
    results.push({ idx, domPath: domPath(el), text });
    idx += 1;
  });
  return results;
}
"""

# srcset is dropped rather than rewritten — its multi-URL/descriptor syntax
# isn't worth the parsing complexity for a v1; the plain src still resolves.
_REWRITE_JS = r"""
(mapping) => {
  for (const [idx, entry] of Object.entries(mapping)) {
    const el = document.querySelector('[data-tu-harvest-idx="' + idx + '"]');
    if (!el) continue;
    el.setAttribute('data-tu-id', entry.tuId);
    el.textContent = entry.targetText;
  }
  document.querySelectorAll('[data-tu-harvest-idx]').forEach((el) => el.removeAttribute('data-tu-harvest-idx'));

  const urlAttrs = [
    ['img', 'src'], ['img', 'srcset'], ['source', 'src'], ['video', 'src'],
    ['audio', 'src'], ['script', 'src'], ['link', 'href'], ['a', 'href'],
  ];
  for (const [tag, attr] of urlAttrs) {
    document.querySelectorAll(tag + '[' + attr + ']').forEach((el) => {
      if (attr === 'srcset') { el.removeAttribute('srcset'); return; }
      try { el.setAttribute(attr, el[attr]); } catch (e) { /* ignore unresolvable */ }
    });
  }
}
"""


class PageFetchError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _unit_key(url: str, dom_path: str, text: str) -> str:
    digest = hashlib.sha256(f"{url}|{dom_path}|{text}".encode("utf-8")).hexdigest()
    return f"page:{digest[:32]}"


async def _check_robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        await asyncio.to_thread(rp.read)
    except Exception:
        return True  # no reachable robots.txt — fail open, most sites have none
    return rp.can_fetch("*", url)


def _inject_sdk(html: str) -> str:
    script = (
        '<script src="/review-sdk/overlay.js"></script>'
        "<script>window.ReviewSDK.initReviewOverlay();</script>"
    )
    if "</body>" in html:
        return html.replace("</body>", f"{script}</body>", 1)
    return html + script


async def fetch_and_render(
    url: str,
    source_language: str,
    target_language: str,
    method: TranslationMethod = TranslationMethod.AI,
) -> PageSnapshot:
    if not url.startswith(("http://", "https://")):
        raise PageFetchError("Only http:// and https:// URLs are supported.", status_code=400)
    if not await _check_robots_allowed(url):
        raise PageFetchError(f"{url} disallows fetching per its robots.txt.", status_code=403)

    db = get_db()

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                except Exception as e:
                    raise PageFetchError(f"Could not load {url}: {e}", status_code=502) from e
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass  # some pages never go idle (polling/websockets) — proceed with what's loaded

                harvested = await page.evaluate(_HARVEST_JS)

                backend = get_translation_backend() if method in (TranslationMethod.AI, TranslationMethod.HYBRID) else None
                agent = await db.get_or_create_agent(
                    name="Human Translator" if method == TranslationMethod.HUMAN else "claude-3-7-sonnet",
                    agent_type="Person" if method == TranslationMethod.HUMAN else "SoftwareAgent",
                    organization=None if method == TranslationMethod.HUMAN else "Anthropic",
                )
                now = datetime.utcnow()

                mapping = {}
                unit_ids: List[str] = []
                for item in harvested:
                    text = _normalize(item["text"])
                    if not text:
                        continue
                    key = _unit_key(url, item["domPath"], text)
                    unit = await db.get_translation_unit_by_source_id(key, target_language)
                    if unit is None:
                        if backend:
                            target_text, confidence = await backend.translate(text, source_language, target_language)
                            status = TranslationStatus.COMPLETED
                        else:
                            target_text, confidence = f"[Awaiting human translation] {text}", 1.0
                            status = TranslationStatus.PENDING
                        unit = TranslationUnit(
                            source_id=key, source_text=text, source_language=source_language,
                            target_text=target_text, target_language=target_language,
                            translation_method=method, translated_by_agent_id=agent.id, translated_at=now,
                            confidence_score=confidence, status=status,
                            metadata={"harvested_from_url": url, "dom_path": item["domPath"]},
                        )
                        await db.save_translation_unit(unit)
                        prov_record = await build_provenance_record(unit, [])
                        await db.save_provenance_record(prov_record)
                    mapping[str(item["idx"])] = {"tuId": unit.id, "targetText": unit.target_text}
                    unit_ids.append(unit.id)

                await page.evaluate(_REWRITE_JS, mapping)
                html = await page.content()
            finally:
                await browser.close()
    except PageFetchError:
        raise
    except Exception as e:
        raise PageFetchError(f"Failed to fetch/render {url}: {e}", status_code=502) from e

    html = _inject_sdk(html)

    snapshot = PageSnapshot(url=url, target_language=target_language, html=html, harvested_unit_ids=unit_ids)
    await db.save_page_snapshot(snapshot)
    return snapshot
