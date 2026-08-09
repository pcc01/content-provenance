"""
Phase 11 — site i18n/l10n/compliance audit API. Crawls a THIRD-PARTY site
(not this system's own translations) and runs pluggable checks: mixed
locales, RTL/logical-CSS readiness, ICU/i18n-tooling usage, privacy-policy
language mismatches. Replaces three standalone scripts the user previously
ran by hand (website_language_reviewer.py, website_language_analyzer.py,
privacy_policy_scraper.py) with a persisted, reviewable equivalent.

POST /api/v1/audit/runs                  - create + run an audit (synchronous, like redrive.py)
GET  /api/v1/audit/runs                  - list past audits
GET  /api/v1/audit/runs/{id}             - status + summary counts
GET  /api/v1/audit/runs/{id}/pages       - the crawled-page inventory
GET  /api/v1/audit/runs/{id}/findings    - filterable findings list
GET  /api/v1/audit/runs/{id}/export      - plain-text report download
GET  /api/v1/audit/runs/{id}/report.pdf  - branded PDF report download
"""

import logging
import re
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field, field_validator

from app.core.audit.report import generate_pdf_report
from app.core.audit.runner import run_audit
from app.core.database import get_db
from app.core.notifications import notify_audit_completed
from app.models.schemas import (
    SiteAudit, SiteAuditCheck, SiteAuditFinding, SiteAuditPage, SiteAuditSeverity,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Deliberately simple (not RFC 5322): this is a lead-capture gate, not a
# deliverability guarantee — good enough to reject obvious typos/garbage
# without adding an email-validator dependency for one field.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuditRunRequest(BaseModel):
    root_url: str
    primary_language: str
    # Required — every report from the public-facing tool is a lead; who
    # requested it and for which URL needs to be captured, not optional.
    requester_email: str
    max_pages: int = Field(40, ge=1, le=200)
    checks: List[SiteAuditCheck] = Field(default_factory=lambda: list(SiteAuditCheck))
    triggered_by: Optional[str] = None
    # Phase 18 — OPTIONAL, and deliberately NOT a field on the persisted
    # SiteAudit model (see crawl_site's docstring): "bring your own
    # authenticated session" for sites that gate content behind a login or
    # bot-detection wall, without this tool storing credentials anywhere.
    # Anonymous crawling (all three omitted) is unchanged and remains the
    # default.
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    auth_cookie: Optional[str] = None  # raw Cookie header value, e.g. copied from browser devtools

    @field_validator("requester_email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError(f"'{v}' doesn't look like a valid email address")
        return v


class AuditRunSummary(BaseModel):
    audit: SiteAudit
    findings_by_check: dict
    findings_by_severity: dict


@router.post("/runs", response_model=SiteAudit)
async def create_audit_run(request: AuditRunRequest):
    """Runs synchronously and returns the completed (or failed) audit —
    same "await the whole run" convention as redrive.py's POST /runs, not a
    background task. A large max_pages means a long HTTP call; see the
    plan's Risks section for why that's an accepted v1 tradeoff."""
    db = get_db()
    audit = SiteAudit(
        root_url=request.root_url, primary_language=request.primary_language,
        requester_email=request.requester_email,
        max_pages=request.max_pages, checks=request.checks, triggered_by=request.triggered_by,
    )
    await db.create_site_audit(audit)
    result = await run_audit(
        audit, auth_username=request.auth_username, auth_password=request.auth_password,
        auth_cookie=request.auth_cookie,
    )
    # Fire-and-forget lead alert — a customer just ran an audit, so notify
    # the site owner. Never let a notification failure surface as a 500
    # for a request that otherwise succeeded.
    try:
        notify_audit_completed(result)
    except Exception:
        logger.exception("notify_audit_completed raised; audit response unaffected")
    return result


@router.get("/runs", response_model=List[SiteAudit])
async def list_audit_runs(limit: int = Query(50, ge=1, le=200)):
    db = get_db()
    return await db.list_site_audits(limit=limit)


@router.get("/runs/{audit_id}", response_model=AuditRunSummary)
async def get_audit_run(audit_id: str):
    db = get_db()
    audit = await db.get_site_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    findings = await db.list_site_audit_findings(audit_id)
    return AuditRunSummary(
        audit=audit,
        findings_by_check=dict(Counter(f.check.value for f in findings)),
        findings_by_severity=dict(Counter(f.severity.value for f in findings)),
    )


@router.get("/runs/{audit_id}/pages", response_model=List[SiteAuditPage])
async def get_audit_pages(audit_id: str):
    db = get_db()
    audit = await db.get_site_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    return await db.list_site_audit_pages(audit_id)


@router.get("/runs/{audit_id}/findings", response_model=List[SiteAuditFinding])
async def get_audit_findings(
    audit_id: str,
    check: Optional[SiteAuditCheck] = Query(None),
    severity: Optional[SiteAuditSeverity] = Query(None),
    page_id: Optional[str] = Query(None),
):
    db = get_db()
    audit = await db.get_site_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    return await db.list_site_audit_findings(audit_id, check=check, severity=severity, page_id=page_id)


@router.get("/runs/{audit_id}/export", response_class=PlainTextResponse)
async def export_audit_report(audit_id: str):
    """Plain-text report, grouped by check then severity — preserves the
    familiar report-file output the original scripts produced, now
    generated from persisted findings instead of being the only artifact."""
    db = get_db()
    audit = await db.get_site_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    findings = await db.list_site_audit_findings(audit_id)

    lines = [
        "=" * 60, "  Site I18n & Compliance Audit Report", "=" * 60, "",
        f"Root URL: {audit.root_url}",
        f"Requested by: {audit.requester_email or 'N/A'}",
        f"Primary language: {audit.primary_language}",
        f"Status: {audit.status.value}",
        f"Pages crawled: {audit.pages_crawled}",
        f"Started: {audit.started_at.isoformat()}",
        f"Finished: {audit.finished_at.isoformat() if audit.finished_at else 'N/A'}",
        f"Total findings: {len(findings)}",
        "",
    ]

    by_check: dict = {}
    for f in findings:
        by_check.setdefault(f.check.value, []).append(f)

    for check_name, items in sorted(by_check.items()):
        lines.append("#" * 60)
        lines.append(f"### {check_name.upper()} ({len(items)} finding(s)) ###")
        lines.append("#" * 60)
        lines.append("")
        for f in items:
            lines.append(f"[{f.severity.value.upper()}] {f.finding_type}: {f.summary}")
            for key, value in f.detail.items():
                lines.append(f"    {key}: {value}")
            lines.append("")

    if not findings:
        lines.append("No issues found.")

    return "\n".join(lines)


@router.get("/runs/{audit_id}/report.pdf")
async def export_audit_pdf_report(audit_id: str):
    """Branded, client-facing PDF — logo, executive summary, findings by
    check with severity coloring. Same underlying findings as /export,
    formatted as something to actually hand a client rather than a .txt
    dump."""
    db = get_db()
    audit = await db.get_site_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
    pages = await db.list_site_audit_pages(audit_id)
    findings = await db.list_site_audit_findings(audit_id)
    pdf_bytes = generate_pdf_report(audit, pages, findings)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="audit-{audit_id[:8]}.pdf"'},
    )
