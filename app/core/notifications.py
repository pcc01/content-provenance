"""
Lead-alert email notifications — fires when a customer runs a site audit
(POST /api/v1/audit/runs) so the site owner knows to follow up with them.
Deliberately built on stdlib smtplib rather than a transactional-email
dependency: one env-var-configured SMTP relay (Gmail app password,
Office365, or any provider's relay) is enough for a low-volume lead alert.

Fails soft everywhere: a broken/unconfigured SMTP setup must never take
down the audit request that triggered it (see notify_audit_completed's
caller in app/api/audit.py, which only logs on False).
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.models.schemas import SiteAudit

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> bool:
    """Best-effort SMTP send. Returns True on success, False on any
    misconfiguration or failure — never raises."""
    if not settings.email_notifications_enabled:
        logger.debug("Email notifications disabled (EMAIL_NOTIFICATIONS_ENABLED=false); skipping.")
        return False
    if not settings.smtp_host or not settings.notify_email_to:
        logger.warning(
            "Email notifications enabled but SMTP_HOST or NOTIFY_EMAIL_TO is unset; skipping send."
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user or "noreply@localhost"
    msg["To"] = settings.notify_email_to
    msg.set_content(body)

    try:
        smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send audit-notification email")
        return False


def notify_audit_completed(audit: SiteAudit) -> bool:
    """Notify the site owner that a customer ran a site audit — this is a
    lead, whether the run succeeded, failed, or was blocked by the target
    site. Called fire-and-forget from POST /api/v1/audit/runs."""
    status_label = audit.status.value.upper()
    subject = f"[Audit lead] {audit.root_url} ({status_label})"

    report_link = ""
    if settings.public_app_url:
        report_link = (
            f"Report: {settings.public_app_url.rstrip('/')}"
            f"/api/v1/audit/runs/{audit.id}/report.pdf\n"
        )

    body = (
        "Someone just ran a site audit — here's a lead to follow up on.\n\n"
        f"Site:              {audit.root_url}\n"
        f"Requested by:      {audit.requester_email or 'N/A'}\n"
        f"Primary language:  {audit.primary_language}\n"
        f"Status:            {status_label}\n"
        f"Pages crawled:     {audit.pages_crawled}\n"
        f"Started:           {audit.started_at.isoformat() if audit.started_at else 'N/A'}\n"
        f"Finished:          {audit.finished_at.isoformat() if audit.finished_at else 'N/A'}\n"
        f"Audit ID:          {audit.id}\n"
        f"{('Error:             ' + audit.error) if audit.error else ''}\n"
        f"{report_link}"
    )
    return send_email(subject, body)
