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
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.core.translation_backends import get_translation_backend
from app.models.schemas import PageSnapshot, TranslationMethod, TranslationStatus, TranslationUnit

_WHITESPACE_RE = re.compile(r"\s+")

# The harvest/rewrite DOM logic itself lives in review-sdk/harvest.ts —
# compiled to this file (`npm run build:sdk` in frontend/) and shared with
# Phase 10's browser extension, rather than kept as a second hand-written
# copy here that could silently drift out of sync with the extension's.
_HARVEST_JS_PATH = Path("frontend/review-sdk/dist/harvest.js")


def _load_harvest_js() -> str:
    if not _HARVEST_JS_PATH.exists():
        raise RuntimeError(
            f"{_HARVEST_JS_PATH} not found — run `npm run build:sdk` in frontend/ to compile "
            "review-sdk/harvest.ts before using the fetch+rewrite page loader."
        )
    return _HARVEST_JS_PATH.read_text(encoding="utf-8")


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
        '<script src="/sdk-dist/overlay.js"></script>'
        "<script>window.ReviewSDK.initReviewOverlay();</script>"
    )
    if "</body>" in html:
        return html.replace("</body>", f"{script}</body>", 1)
    return html + script


async def match_or_create_units(
    url: str,
    source_language: str,
    target_language: str,
    method: TranslationMethod,
    harvested: List[dict],
    now: "datetime | None" = None,
) -> "tuple[dict, List[str]]":
    """The matching step shared by `fetch_and_render` (Playwright-driven,
    below) and Phase 10's `POST /api/v1/pages/harvest` (extension-driven —
    no headless browser involved at all, since the real tab already IS the
    browser; the content script does its own DOM walk and hands this
    function the same {idx, domPath, text} shape Playwright's harvest JS
    produces). Matches each item against an existing TranslationUnit by
    content hash, or creates+translates a new one. Returns
    ({idx: {tuId, targetText}}, [unit_id, ...]).

    `now` is a parameter (not just computed here) so fetch_and_render can
    pass the SAME timestamp it stamps its PageSnapshot.fetched_at with —
    see that function's comment on why those two have to match exactly.
    Phase 10's caller has no snapshot to keep in sync with, so it just
    leaves this as the default (a fresh datetime.utcnow())."""
    if now is None:
        now = datetime.utcnow()
    db = get_db()
    backend = get_translation_backend() if method in (TranslationMethod.AI, TranslationMethod.HYBRID) else None
    agent = await db.get_or_create_agent(
        name="Human Translator" if method == TranslationMethod.HUMAN else "claude-3-7-sonnet",
        agent_type="Person" if method == TranslationMethod.HUMAN else "SoftwareAgent",
        organization=None if method == TranslationMethod.HUMAN else "Anthropic",
    )

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

    return mapping, unit_ids


async def fetch_and_render(
    url: str,
    source_language: str,
    target_language: str,
    method: TranslationMethod = TranslationMethod.AI,
    # Phase 18 — same optional, non-persisted "bring your own authenticated
    # session" as app/core/audit/crawler.py's crawl_site — HTTP Basic Auth
    # and/or a raw Cookie header, applied to this one fetch only. Anonymous
    # fetching (all three None, the default) is unchanged.
    auth_username: Optional[str] = None, auth_password: Optional[str] = None,
    auth_cookie: Optional[str] = None,
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
                context_kwargs: dict = {}
                if auth_username and auth_password:
                    context_kwargs["http_credentials"] = {"username": auth_username, "password": auth_password}
                if auth_cookie:
                    context_kwargs["extra_http_headers"] = {"Cookie": auth_cookie}
                context = await browser.new_context(**context_kwargs)
                try:
                    page = await context.new_page()
                    try:
                        await page.goto(url, wait_until="load", timeout=30000)
                    except Exception as e:
                        raise PageFetchError(f"Could not load {url}: {e}", status_code=502) from e
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass  # some pages never go idle (polling/websockets) — proceed with what's loaded

                    await page.add_script_tag(content=_load_harvest_js())
                    harvested = await page.evaluate("() => window.ReviewHarvest.harvest()")
                    now = datetime.utcnow()
                    mapping, unit_ids = await match_or_create_units(
                        url, source_language, target_language, method, harvested, now=now,
                    )

                    # swapText=true: Phase 8's rendered pages are served from a
                    # different origin than the original, so both the visible
                    # text and asset URLs need rewriting (unlike Phase 10's
                    # live-tab mode, which only tags elements — see harvest.ts).
                    await page.evaluate("(mapping) => window.ReviewHarvest.rewrite(mapping, true)", mapping)
                    html = await page.content()
                finally:
                    await context.close()
            finally:
                await browser.close()
    except PageFetchError:
        raise
    except Exception as e:
        raise PageFetchError(f"Failed to fetch/render {url}: {e}", status_code=502) from e

    html = _inject_sdk(html)

    # fetched_at deliberately set to the SAME `now` used for every harvested
    # unit's translated_at/version created_at above, not a fresh
    # datetime.utcnow() here — Phase 9's as_of reconstruction picks the
    # newest template with fetched_at <= as_of, and a few milliseconds of
    # drift between "when the units were stamped" and "when the snapshot
    # itself was stamped" would make as_of=<this fetch's own timestamp>
    # incorrectly find no template yet.
    snapshot = PageSnapshot(
        url=url, target_language=target_language, html=html, harvested_unit_ids=unit_ids, fetched_at=now,
    )
    await db.save_page_snapshot(snapshot)
    return snapshot
