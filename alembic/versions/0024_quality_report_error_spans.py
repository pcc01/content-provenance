"""Phase 6 — quality_report_items.error_spans: XCOMET localized error spans
attached to a report after the fact via POST /quality/reports/{id}/attach-xcomet.
Optional, non-commercial signal (CC-BY-NC-SA-4.0 checkpoint).

Revision ID: 0024_quality_report_error_spans
Revises: 0023_redrive_second_review
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0024_quality_report_error_spans"
down_revision: Union[str, None] = "0023_redrive_second_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quality_report_items",
        sa.Column("error_spans", sa.JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("quality_report_items", "error_spans")
