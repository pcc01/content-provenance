"""Phase 13 — redrive_runs gains a second, independent threshold axis:
style_threshold (+ the style_guide_id to score against). A unit redrives
if EITHER its quality score falls below `threshold` OR its style score
falls below `style_threshold` — see app/core/redrive/engine.py.

Revision ID: 0018_redrive_style_threshold
Revises: 0017_style_adherence_scores
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_redrive_style_threshold"
down_revision: Union[str, None] = "0017_style_adherence_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("redrive_runs", sa.Column("style_threshold", sa.Float, nullable=True))
    op.add_column("redrive_runs", sa.Column("style_guide_id", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("redrive_runs", "style_guide_id")
    op.drop_column("redrive_runs", "style_threshold")
