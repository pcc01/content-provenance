"""Phase 7 — document_shapes: per-slide text shape geometry for the
layout-aware deck review. One row per text-bearing shape (or speaker-note
paragraph) of an imported .pptx; the shape's text lives on its linked
TranslationUnit, same as every other document segment.

Revision ID: 0025_document_shapes
Revises: 0024_quality_report_error_spans
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0025_document_shapes"
down_revision: Union[str, None] = "0024_quality_report_error_spans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_shapes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column("page_width", sa.Float, nullable=False),
        sa.Column("page_height", sa.Float, nullable=False),
        sa.Column("shape_index", sa.Integer, nullable=False),
        sa.Column("reading_order", sa.Integer, nullable=False),
        sa.Column("kind", sa.String, nullable=False, server_default="other"),
        sa.Column("x", sa.Float, nullable=True),
        sa.Column("y", sa.Float, nullable=True),
        sa.Column("w", sa.Float, nullable=True),
        sa.Column("h", sa.Float, nullable=True),
        sa.Column("unit_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_document_shapes_document_id", "document_shapes", ["document_id"])
    op.create_index("ix_document_shapes_page_index", "document_shapes", ["page_index"])
    op.create_index("ix_document_shapes_unit_id", "document_shapes", ["unit_id"])


def downgrade() -> None:
    op.drop_index("ix_document_shapes_unit_id", table_name="document_shapes")
    op.drop_index("ix_document_shapes_page_index", table_name="document_shapes")
    op.drop_index("ix_document_shapes_document_id", table_name="document_shapes")
    op.drop_table("document_shapes")
