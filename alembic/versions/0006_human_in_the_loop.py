"""Human-in-the-loop redrive approval: require_human_approval on redrive_runs,
proposed_text/approved_by/approved_at on redrive_run_items.

Revision ID: 0006_human_in_the_loop
Revises: 0005_drop_bundle_unit_fk
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_human_in_the_loop"
down_revision: Union[str, None] = "0005_drop_bundle_unit_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "redrive_runs",
        sa.Column("require_human_approval", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("redrive_run_items", sa.Column("proposed_text", sa.Text, nullable=True))
    op.add_column("redrive_run_items", sa.Column("approved_by", sa.String, nullable=True))
    op.add_column("redrive_run_items", sa.Column("approved_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("redrive_run_items", "approved_at")
    op.drop_column("redrive_run_items", "approved_by")
    op.drop_column("redrive_run_items", "proposed_text")
    op.drop_column("redrive_runs", "require_human_approval")
