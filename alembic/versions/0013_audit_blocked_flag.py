"""Flag audits that failed because the target site blocked automated
crawling (robots.txt disallow, bot-detection/CAPTCHA interstitial) —
distinct from other failures (bad URL, network timeout). The public
landing page uses this to show a consultative "we'll follow up
personally" message instead of a flat error for a visitor who was
curious enough to submit their site.

Revision ID: 0013_audit_blocked_flag
Revises: 0012_audit_requester_email
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_audit_blocked_flag"
down_revision: Union[str, None] = "0012_audit_requester_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "site_audits",
        sa.Column("blocked", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("site_audits", "blocked")
