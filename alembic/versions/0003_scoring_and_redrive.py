"""Quality scoring + redrive engine tables.

Revision ID: 0003_scoring_and_redrive
Revises: 0002_ingest_events
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_scoring_and_redrive"
down_revision: Union[str, None] = "0002_ingest_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_scores",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("version_id", sa.String, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("scorer", sa.String, nullable=False),
        sa.Column("reasons", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("errors", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("scored_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_quality_scores_unit_id", "quality_scores", ["unit_id"])

    op.create_table(
        "redrive_runs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("threshold", sa.Float, nullable=False),
        sa.Column("scope", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("scoring_provider", sa.String, nullable=False),
        sa.Column("redrive_provider", sa.String, nullable=False),
        sa.Column("triggered_by", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("summary", sa.JSON, nullable=False, server_default="{}"),
    )

    op.create_table(
        "redrive_run_items",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("redrive_runs.id"), nullable=False),
        sa.Column("unit_id", sa.String, nullable=False),
        sa.Column("before_score", sa.Float, nullable=True),
        sa.Column("after_score", sa.Float, nullable=True),
        sa.Column("outcome", sa.String, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
    )
    op.create_index("ix_redrive_run_items_run_id", "redrive_run_items", ["run_id"])
    op.create_index("ix_redrive_run_items_unit_id", "redrive_run_items", ["unit_id"])

    op.create_table(
        "provider_usage_ledger",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("period", sa.String, nullable=False),
        sa.Column("scope", sa.String, nullable=False, server_default="month"),
        sa.Column("limit_chars", sa.Integer, nullable=False),
        sa.Column("used_chars", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_provider_usage_ledger_provider", "provider_usage_ledger", ["provider"])


def downgrade() -> None:
    op.drop_table("provider_usage_ledger")
    op.drop_table("redrive_run_items")
    op.drop_table("redrive_runs")
    op.drop_table("quality_scores")
