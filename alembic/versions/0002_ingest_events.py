"""Ingest events — the "entering/leaving the system" ledger.

Revision ID: 0002_ingest_events
Revises: 0001_initial
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_ingest_events"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("format", sa.String, nullable=False, server_default="xliff"),
        sa.Column("source_system", sa.String, nullable=True),
        sa.Column("xliff_document_id", sa.String, nullable=True),
        sa.Column("unit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_ingest_events_created_at", "ingest_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("ingest_events")
