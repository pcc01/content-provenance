"""
Phase 11 — orchestrates one full audit run: crawl -> persist the page
inventory -> run each enabled check -> persist findings -> mark
complete/failed. Called synchronously (awaited) by POST /api/v1/audit/runs,
matching redrive.py's existing "await the whole run" convention rather than
adding background-task infrastructure — see the plan's Risks section on
why that's an accepted v1 tradeoff.
"""

from datetime import datetime
from typing import Dict
from urllib.parse import urlparse

from app.core.audit.checks import (
    cookie_consent, font_coverage, hreflang, icu_i18n, locale_format, locale_switcher,
    mixed_locale, payment_localization, placeholder_leak, privacy, rtl_readiness,
    seo_metadata, text_expansion, translation_coverage,
)
from app.core.audit.checks.mixed_locale import _detect, _locale_from_path
from app.core.audit.crawler import crawl_site
from app.core.database import get_db
from app.core.page_fetch import PageFetchError
from app.models.schemas import SiteAudit, SiteAuditCheck, SiteAuditPage, SiteAuditStatus

_CHECK_MODULES = {
    SiteAuditCheck.MIXED_LOCALE: mixed_locale,
    SiteAuditCheck.RTL_READINESS: rtl_readiness,
    SiteAuditCheck.ICU_I18N: icu_i18n,
    SiteAuditCheck.PRIVACY: privacy,
    SiteAuditCheck.TEXT_EXPANSION: text_expansion,
    SiteAuditCheck.FONT_COVERAGE: font_coverage,
    SiteAuditCheck.HREFLANG: hreflang,
    SiteAuditCheck.COOKIE_CONSENT: cookie_consent,
    SiteAuditCheck.PLACEHOLDER_LEAK: placeholder_leak,
    SiteAuditCheck.LOCALE_FORMAT: locale_format,
    SiteAuditCheck.TRANSLATION_COVERAGE: translation_coverage,
    SiteAuditCheck.LOCALE_SWITCHER: locale_switcher,
    SiteAuditCheck.SEO_METADATA: seo_metadata,
    SiteAuditCheck.PAYMENT_LOCALIZATION: payment_localization,
}


async def run_audit(audit: SiteAudit) -> SiteAudit:
    db = get_db()
    await db.update_site_audit(audit.id, status=SiteAuditStatus.RUNNING)

    try:
        crawled_pages = await crawl_site(audit.root_url, max_pages=audit.max_pages)
    except PageFetchError as e:
        await db.update_site_audit(
            audit.id, status=SiteAuditStatus.FAILED, finished_at=datetime.utcnow(), error=str(e),
        )
        audit.status = SiteAuditStatus.FAILED
        audit.error = str(e)
        return audit

    expected_primary = audit.primary_language.split("-")[0].lower()
    page_ids: Dict[str, str] = {}
    for cp in crawled_pages:
        detected = _detect(" ".join(cp.text_blocks)[:5000])
        expected = _locale_from_path(urlparse(cp.url).path) or expected_primary
        saved = await db.add_site_audit_page(SiteAuditPage(
            audit_id=audit.id, url=cp.url, html_lang_attr=cp.html_lang,
            expected_locale=expected, detected_language=detected, status_code=cp.status_code,
        ))
        page_ids[cp.url] = saved.id

    for check in audit.checks:
        module = _CHECK_MODULES.get(check)
        if module is None:
            continue
        for finding in module.run(crawled_pages, page_ids, audit):
            await db.add_site_audit_finding(finding)

    await db.update_site_audit(
        audit.id, status=SiteAuditStatus.COMPLETED, finished_at=datetime.utcnow(),
        pages_crawled=len(crawled_pages),
    )
    audit.status = SiteAuditStatus.COMPLETED
    audit.pages_crawled = len(crawled_pages)
    return audit
