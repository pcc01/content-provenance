"""Phase 13 — style guides, style guide rules, glossary terms. See
docs/graphrag-provenance-proposal.md and ROADMAP.md's Phase 13 entry.

Revision ID: 0014_style_guides_and_glossary
Revises: 0013_audit_blocked_flag
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_style_guides_and_glossary"
down_revision: Union[str, None] = "0013_audit_blocked_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Needed by 0016's embedding columns too — created here, first, so every
    # later Phase 13 migration in the same run can assume it already exists.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "style_guides",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False, server_default="1.0"),
        sa.Column("locale", sa.String, nullable=True),
        sa.Column("voice_description", sa.Text, nullable=True),
        sa.Column("tone_attributes", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("supersedes_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("created_by", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_style_guides_locale", "style_guides", ["locale"])

    op.create_table(
        "style_guide_rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("style_guide_id", sa.String, sa.ForeignKey("style_guides.id"), nullable=False),
        sa.Column("rule_type", sa.String, nullable=False),
        sa.Column("rule_text", sa.Text, nullable=False),
        sa.Column("severity", sa.String, nullable=False, server_default="minor"),
        sa.Column("applies_to_locale", sa.String, nullable=True),
        sa.Column("source_term", sa.String, nullable=True),
        sa.Column("target_term", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_style_guide_rules_style_guide_id", "style_guide_rules", ["style_guide_id"])
    op.create_index("ix_style_guide_rules_applies_to_locale", "style_guide_rules", ["applies_to_locale"])

    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("style_guide_id", sa.String, sa.ForeignKey("style_guides.id"), nullable=True),
        sa.Column("source_term", sa.String, nullable=False),
        sa.Column("target_term", sa.String, nullable=True),
        sa.Column("locale", sa.String, nullable=True),
        sa.Column("do_not_translate", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_glossary_terms_style_guide_id", "glossary_terms", ["style_guide_id"])
    op.create_index("ix_glossary_terms_source_term", "glossary_terms", ["source_term"])
    op.create_index("ix_glossary_terms_locale", "glossary_terms", ["locale"])


def downgrade() -> None:
    op.drop_table("glossary_terms")
    op.drop_table("style_guide_rules")
    op.drop_table("style_guides")
    # Extension deliberately left in place on downgrade — 0016 also depends
    # on it and dropping/recreating it mid-chain risks another database
    # object still referencing it.
