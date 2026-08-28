"""Phase 1 (report-gated redrive) — quality_reports + quality_report_items:
the persisted, exportable "produce a report" step that sits between
evaluate and redrive. Parent-run/child-rows shape, same as
redrive_runs/redrive_run_items and site_audits/site_audit_pages.

Revision ID: 0021_quality_reports
Revises: 0020_automatic_metric_scores
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0021_quality_reports"
down_revision: Union[str, None] = "0020_automatic_metric_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("scope", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("quality_threshold", sa.Float, nullable=False),
        sa.Column("style_threshold", sa.Float, nullable=True),
        sa.Column("style_guide_id", sa.String, nullable=True),
        sa.Column("scoring_provider", sa.String, nullable=False),
        sa.Column("scoring_model", sa.String, nullable=True),
        sa.Column("reference_mode", sa.String, nullable=True),
        sa.Column("triggered_by", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("summary", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("totals", sa.JSON, nullable=False, server_default="{}"),
    )

    op.create_table(
        "quality_report_items",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("report_id", sa.String, sa.ForeignKey("quality_reports.id"), nullable=False),
        sa.Column("unit_id", sa.String, nullable=False),
        sa.Column("quality_score_id", sa.String, nullable=True),
        sa.Column("scorer", sa.String, nullable=False),
        sa.Column("before_score", sa.Float, nullable=True),
        sa.Column("style_score", sa.Float, nullable=True),
        sa.Column("reasons", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("errors", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("hard_fail", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("bucket", sa.String, nullable=False),
        sa.Column("recommended_action", sa.String, nullable=False),
        sa.Column("route_override", sa.String, nullable=True),
        sa.Column("commercial_safe", sa.Boolean, nullable=True),
        sa.Column("source_text_len", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_quality_report_items_report_id", "quality_report_items", ["report_id"])
    op.create_index("ix_quality_report_items_unit_id", "quality_report_items", ["unit_id"])
    op.create_index("ix_quality_report_items_bucket", "quality_report_items", ["bucket"])


def downgrade() -> None:
    op.drop_index("ix_quality_report_items_bucket", table_name="quality_report_items")
    op.drop_index("ix_quality_report_items_unit_id", table_name="quality_report_items")
    op.drop_index("ix_quality_report_items_report_id", table_name="quality_report_items")
    op.drop_table("quality_report_items")
    op.drop_table("quality_reports")
