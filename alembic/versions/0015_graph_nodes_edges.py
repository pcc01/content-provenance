"""Phase 13 — graph_nodes/graph_edges: the pgGraph layer, plain relational
tables (Apache AGE evaluated and deferred — see
docs/graphrag-provenance-proposal.md §3).

Revision ID: 0015_graph_nodes_edges
Revises: 0014_style_guides_and_glossary
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_graph_nodes_edges"
down_revision: Union[str, None] = "0014_style_guides_and_glossary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("node_type", sa.String, nullable=False),
        sa.Column("ref_table", sa.String, nullable=False),
        sa.Column("ref_id", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("properties", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_graph_nodes_node_type", "graph_nodes", ["node_type"])
    op.create_index("ix_graph_nodes_ref_id", "graph_nodes", ["ref_id"])
    # One node per (node_type, ref_id) — repeated writes to the same
    # underlying row (e.g. re-scoring a unit) must upsert, never duplicate.
    op.create_unique_constraint("uq_graph_nodes_type_ref", "graph_nodes", ["node_type", "ref_id"])

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("src_node_id", sa.String, sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("dst_node_id", sa.String, sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("edge_type", sa.String, nullable=False),
        sa.Column("properties", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_graph_edges_src_node_id", "graph_edges", ["src_node_id"])
    op.create_index("ix_graph_edges_dst_node_id", "graph_edges", ["dst_node_id"])
    op.create_index("ix_graph_edges_edge_type", "graph_edges", ["edge_type"])


def downgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
