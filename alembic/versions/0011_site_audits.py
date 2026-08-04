"""Site audits (Phase 11) — crawl a third-party site for mixed-locale
content, RTL/logical-CSS readiness, ICU/i18n-tooling usage, and privacy-
policy language mismatches. Three tables mirroring RedriveRun/RedriveRunItem's
parent-run + child-rows shape, one level deeper for the crawled-page
inventory.

Revision ID: 0011_site_audits
Revises: 0010_page_level_notes
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_site_audits"
down_revision: Union[str, None] = "0010_page_level_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_audits",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("root_url", sa.String, nullable=False),
        sa.Column("primary_language", sa.String, nullable=False),
        sa.Column("max_pages", sa.Integer, nullable=False, server_default="40"),
        sa.Column("checks", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("triggered_by", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("pages_crawled", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
    )

    op.create_table(
        "site_audit_pages",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("audit_id", sa.String, sa.ForeignKey("site_audits.id"), nullable=False),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("html_lang_attr", sa.String, nullable=True),
        sa.Column("expected_locale", sa.String, nullable=True),
        sa.Column("detected_language", sa.String, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_site_audit_pages_audit_id", "site_audit_pages", ["audit_id"])

    op.create_table(
        "site_audit_findings",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("audit_id", sa.String, sa.ForeignKey("site_audits.id"), nullable=False),
        sa.Column("page_id", sa.String, sa.ForeignKey("site_audit_pages.id"), nullable=True),
        sa.Column("check", sa.String, nullable=False),
        sa.Column("finding_type", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False, server_default="warning"),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_site_audit_findings_audit_id", "site_audit_findings", ["audit_id"])
    op.create_index("ix_site_audit_findings_page_id", "site_audit_findings", ["page_id"])
    op.create_index("ix_site_audit_findings_check", "site_audit_findings", ["check"])


def downgrade() -> None:
    op.drop_index("ix_site_audit_findings_check", table_name="site_audit_findings")
    op.drop_index("ix_site_audit_findings_page_id", table_name="site_audit_findings")
    op.drop_index("ix_site_audit_findings_audit_id", table_name="site_audit_findings")
    op.drop_table("site_audit_findings")
    op.drop_index("ix_site_audit_pages_audit_id", table_name="site_audit_pages")
    op.drop_table("site_audit_pages")
    op.drop_table("site_audits")
