"""Phase 15 — automatic_metric_scores: METEOR/COMET-Kiwi, a third
independent scoring axis alongside quality_scores (LLM-judge accuracy)
and style_adherence_scores (LLM-judge tone/voice). See
docs/quality-evaluation-research.md §7.

Revision ID: 0020_automatic_metric_scores
Revises: 0019_quality_score_hard_fail
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020_automatic_metric_scores"
down_revision: Union[str, None] = "0019_quality_score_hard_fail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automatic_metric_scores",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("metric", sa.String, nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("raw_score", sa.Float, nullable=True),
        sa.Column("reference_type", sa.String, nullable=True),
        sa.Column("reference_unit_version_id", sa.String, nullable=True),
        sa.Column("detail", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("scored_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_automatic_metric_scores_unit_id", "automatic_metric_scores", ["unit_id"])
    op.create_index("ix_automatic_metric_scores_metric", "automatic_metric_scores", ["metric"])


def downgrade() -> None:
    op.drop_table("automatic_metric_scores")
