"""Phase 13 — translation_exemplars (vendor TM / approved-translation
retrieval context) and pgvector embedding columns on style_guide_rules /
glossary_terms / translation_exemplars. Embedding dimension (384) matches
EMBEDDING_MODEL's default (sentence-transformers/all-MiniLM-L6-v2) — see
app/core/db/models.py's EMBEDDING_DIM.

Revision ID: 0016_exemplars_and_embeddings
Revises: 0015_graph_nodes_edges
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0016_exemplars_and_embeddings"
down_revision: Union[str, None] = "0015_graph_nodes_edges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.create_table(
        "translation_exemplars",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("target_text", sa.Text, nullable=False),
        sa.Column("source_language", sa.String, nullable=False),
        sa.Column("target_language", sa.String, nullable=False),
        sa.Column("origin", sa.String, nullable=False, server_default="vendor"),
        sa.Column("origin_agent_id", sa.String, nullable=True),
        sa.Column("style_guide_id", sa.String, nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_translation_exemplars_source_language", "translation_exemplars", ["source_language"])
    op.create_index("ix_translation_exemplars_target_language", "translation_exemplars", ["target_language"])
    op.create_index("ix_translation_exemplars_origin_agent_id", "translation_exemplars", ["origin_agent_id"])

    op.add_column("style_guide_rules", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.add_column("glossary_terms", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))


def downgrade() -> None:
    op.drop_column("glossary_terms", "embedding")
    op.drop_column("style_guide_rules", "embedding")
    op.drop_table("translation_exemplars")
