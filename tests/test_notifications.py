"""
Tests for the audit-lead email notification (app/core/notifications.py).
Mocks smtplib entirely — no real SMTP connection is ever made.
Run with: PYTHONPATH=. pytest tests/test_notifications.py -v
"""

from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.notifications import notify_audit_completed, send_email
from app.models.schemas import SiteAudit, SiteAuditStatus


def _configure_smtp(monkeypatch, **overrides):
    defaults = dict(
        email_notifications_enabled=True,
        notify_email_to="admin@thewordinbits.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",
        smtp_from="user@example.com",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        public_app_url="",
    )
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def test_send_email_noop_when_disabled(monkeypatch):
    _configure_smtp(monkeypatch, email_notifications_enabled=False)
    with patch("smtplib.SMTP") as smtp_cls:
        assert send_email("subject", "body") is False
        smtp_cls.assert_not_called()


def test_send_email_noop_when_unconfigured(monkeypatch):
    _configure_smtp(monkeypatch, smtp_host="")
    with patch("smtplib.SMTP") as smtp_cls:
        assert send_email("subject", "body") is False
        smtp_cls.assert_not_called()


def test_send_email_sends_via_smtp_starttls(monkeypatch):
    _configure_smtp(monkeypatch)
    server = MagicMock()
    server.__enter__.return_value = server
    with patch("smtplib.SMTP", return_value=server) as smtp_cls:
        assert send_email("Hello", "World") is True
        smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user@example.com", "secret")
        server.send_message.assert_called_once()
        sent_msg = server.send_message.call_args[0][0]
        assert sent_msg["Subject"] == "Hello"
        assert sent_msg["To"] == "admin@thewordinbits.com"


def test_send_email_returns_false_on_smtp_failure(monkeypatch):
    _configure_smtp(monkeypatch)
    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        assert send_email("subject", "body") is False


def test_notify_audit_completed_includes_report_link(monkeypatch):
    _configure_smtp(monkeypatch, public_app_url="https://audit.thewordinbits.com")
    audit = SiteAudit(
        root_url="https://customer-site.com",
        primary_language="en",
        requester_email="lead@customer-site.com",
        status=SiteAuditStatus.COMPLETED,
        pages_crawled=12,
    )
    server = MagicMock()
    server.__enter__.return_value = server
    with patch("smtplib.SMTP", return_value=server):
        assert notify_audit_completed(audit) is True
        sent_msg = server.send_message.call_args[0][0]
        assert "customer-site.com" in sent_msg["Subject"]
        body = sent_msg.get_content()
        assert "lead@customer-site.com" in body
        assert f"/api/v1/audit/runs/{audit.id}/report.pdf" in body
