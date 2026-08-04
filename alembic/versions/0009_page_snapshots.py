"""Page snapshots — Phase 8 non-cooperative (fetch + rewrite) page review.
Append-only: a re-fetch inserts a new row so Phase 9's time-travel can
reconstruct past structure, not just the latest.

Revision ID: 0009_page_snapshots
Revises: 0008_documents
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_page_snapshots"
down_revision: Union[str, None] = "0008_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "page_snapshots",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("target_language", sa.String, nullable=False),
        sa.Column("html", sa.Text, nullable=False),
        sa.Column("harvested_unit_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_page_snapshots_url", "page_snapshots", ["url"])
    op.create_index("ix_page_snapshots_target_language", "page_snapshots", ["target_language"])
    op.create_index("ix_page_snapshots_fetched_at", "page_snapshots", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("page_snapshots")
