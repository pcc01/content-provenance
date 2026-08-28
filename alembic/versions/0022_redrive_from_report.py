"""Phase 3 (report-gated redrive) — redrive_runs.from_report_id + routing:
a run launched from a saved QualityReport instead of re-scoring a scope,
with the per-bucket / per-unit RedriveRouting it used.

Revision ID: 0022_redrive_from_report
Revises: 0021_quality_reports
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0022_redrive_from_report"
down_revision: Union[str, None] = "0021_quality_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("redrive_runs", sa.Column("from_report_id", sa.String, nullable=True))
    op.add_column("redrive_runs", sa.Column("routing", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("redrive_runs", "routing")
    op.drop_column("redrive_runs", "from_report_id")
