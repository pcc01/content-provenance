"""Phase 15 — quality_scores gains hard_fail (MQM's "any critical error ->
automatic Fail" rule, decoupled from the numeric score). See
docs/quality-evaluation-research.md and app/core/scoring/claude_scorer.py.

Revision ID: 0019_quality_score_hard_fail
Revises: 0018_redrive_style_threshold
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019_quality_score_hard_fail"
down_revision: Union[str, None] = "0018_redrive_style_threshold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quality_scores",
        sa.Column("hard_fail", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("quality_scores", "hard_fail")
