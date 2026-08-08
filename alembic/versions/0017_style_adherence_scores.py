"""Phase 13 — style_adherence_scores: the tone/voice/style analogue of
quality_scores (same 0-100, lower-is-worse convention).

Revision ID: 0017_style_adherence_scores
Revises: 0016_exemplars_and_embeddings
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_style_adherence_scores"
down_revision: Union[str, None] = "0016_exemplars_and_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "style_adherence_scores",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("style_guide_id", sa.String, nullable=True),
        sa.Column("tone_score", sa.Float, nullable=True),
        sa.Column("voice_score", sa.Float, nullable=True),
        sa.Column("terminology_score", sa.Float, nullable=True),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("scorer", sa.String, nullable=False),
        sa.Column("reasons", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("scored_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_style_adherence_scores_unit_id", "style_adherence_scores", ["unit_id"])
    op.create_index("ix_style_adherence_scores_style_guide_id", "style_adherence_scores", ["style_guide_id"])


def downgrade() -> None:
    op.drop_table("style_adherence_scores")
