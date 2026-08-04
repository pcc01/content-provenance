"""Capture the requester's email on a site audit run (Phase 12 —
lead-capture for the consulting-facing audit tool: every public report is
a lead, so who requested it and for which URL needs to persist).

Revision ID: 0012_audit_requester_email
Revises: 0011_site_audits
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_audit_requester_email"
down_revision: Union[str, None] = "0011_site_audits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("site_audits", sa.Column("requester_email", sa.String, nullable=True))
    op.create_index("ix_site_audits_requester_email", "site_audits", ["requester_email"])


def downgrade() -> None:
    op.drop_index("ix_site_audits_requester_email", table_name="site_audits")
    op.drop_column("site_audits", "requester_email")
