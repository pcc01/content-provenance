"""Documents — Phase 7a plain text/Markdown in-context review. Segments are
ordinary translation_units rows (metadata carries document_id + position),
so this migration only needs the container table.

Revision ID: 0008_documents
Revises: 0007_review_notes
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_documents"
down_revision: Union[str, None] = "0007_review_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("original_filename", sa.String, nullable=True),
        sa.Column("format", sa.String, nullable=False),
        sa.Column("source_language", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("uploaded_by", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("documents")
