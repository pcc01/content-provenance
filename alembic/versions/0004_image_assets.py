"""Image assets — context screenshots + translatable image units.

Revision ID: 0004_image_assets
Revises: 0003_scoring_and_redrive
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_image_assets"
down_revision: Union[str, None] = "0003_scoring_and_redrive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_assets",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("storage_path", sa.String, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("checksum", sa.String, nullable=False),
        sa.Column("original_filename", sa.String, nullable=True),
        sa.Column("alt_text", sa.String, nullable=True),
        sa.Column("uploaded_at", sa.DateTime, nullable=False),
        sa.Column("uploaded_by", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_image_assets_checksum", "image_assets", ["checksum"])

    op.create_table(
        "image_translation_units",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_image_id", sa.String, sa.ForeignKey("image_assets.id"), nullable=False),
        sa.Column("target_image_id", sa.String, sa.ForeignKey("image_assets.id"), nullable=True),
        sa.Column("source_language", sa.String, nullable=False),
        sa.Column("target_language", sa.String, nullable=False),
        sa.Column("translation_method", sa.String, nullable=False),
        sa.Column("translated_by_agent_id", sa.String, nullable=False),
        sa.Column("translated_at", sa.DateTime, nullable=True),
        sa.Column("reviewed_by_agent_id", sa.String, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("overlay_text_unit_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("prov_entity_id", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_image_translation_units_source_image_id", "image_translation_units", ["source_image_id"])

    op.create_table(
        "image_context_links",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("image_id", sa.String, sa.ForeignKey("image_assets.id"), nullable=False),
        sa.Column("translation_unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("note", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_image_context_links_image_id", "image_context_links", ["image_id"])
    op.create_index("ix_image_context_links_translation_unit_id", "image_context_links", ["translation_unit_id"])


def downgrade() -> None:
    op.drop_table("image_context_links")
    op.drop_table("image_translation_units")
    op.drop_table("image_assets")
