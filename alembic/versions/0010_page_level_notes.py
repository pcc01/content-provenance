"""Page-level notes (Phase 10) — review_notes.unit_id becomes nullable,
add page_url/target_language so a note can attach to a whole page instead
of one segment.

Revision ID: 0010_page_level_notes
Revises: 0009_page_snapshots
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_page_level_notes"
down_revision: Union[str, None] = "0009_page_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("review_notes", "unit_id", existing_type=sa.String, nullable=True)
    op.add_column("review_notes", sa.Column("page_url", sa.String, nullable=True))
    op.add_column("review_notes", sa.Column("target_language", sa.String, nullable=True))
    op.create_index("ix_review_notes_page_url", "review_notes", ["page_url"])


def downgrade() -> None:
    op.drop_index("ix_review_notes_page_url", table_name="review_notes")
    op.drop_column("review_notes", "target_language")
    op.drop_column("review_notes", "page_url")
    op.alter_column("review_notes", "unit_id", existing_type=sa.String, nullable=False)
