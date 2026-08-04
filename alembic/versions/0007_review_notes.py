"""Review notes — the notes thread in the review UI's segment drawer.

Revision ID: 0007_review_notes
Revises: 0006_human_in_the_loop
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_review_notes"
down_revision: Union[str, None] = "0006_human_in_the_loop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_notes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, nullable=False),
        sa.Column("author", sa.String, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("parent_id", sa.String, nullable=True),
    )
    op.create_index("ix_review_notes_unit_id", "review_notes", ["unit_id"])


def downgrade() -> None:
    op.drop_table("review_notes")
