"""Phase 4 (report-gated redrive) — redrive_runs.second_review: hold an mt
redrive candidate for a human sign-off (always, when set) or when its
second-pass score doesn't clear the report threshold (default).

Revision ID: 0023_redrive_second_review
Revises: 0022_redrive_from_report
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0023_redrive_second_review"
down_revision: Union[str, None] = "0022_redrive_from_report"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "redrive_runs",
        sa.Column("second_review", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("redrive_runs", "second_review")
