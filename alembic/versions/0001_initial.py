"""Initial schema — agents, projects, translation units + version history,
deployments, provenance (bundles/entities/activities/relations), xliff documents.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provenance_agents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("agent_type", sa.String, nullable=False),
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("organization", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_provenance_agents_name", "provenance_agents", ["name"])

    op.create_table(
        "translation_projects",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_language", sa.String, nullable=False),
        sa.Column("target_languages", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("context", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("created_by", sa.String, nullable=True),
        sa.Column("translation_units", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )

    op.create_table(
        "translation_units",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("source_language", sa.String, nullable=False),
        sa.Column("target_text", sa.Text, nullable=True),
        sa.Column("target_language", sa.String, nullable=False),
        sa.Column("translation_method", sa.String, nullable=False),
        sa.Column("translated_by_agent_id", sa.String, nullable=False),
        sa.Column("translated_at", sa.DateTime, nullable=True),
        sa.Column("reviewed_by_agent_id", sa.String, nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("prov_entity_id", sa.String, nullable=True),
        sa.Column("project_id", sa.String, sa.ForeignKey("translation_projects.id"), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_translation_units_project_id", "translation_units", ["project_id"])

    op.create_table(
        "translation_unit_versions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("target_text", sa.Text, nullable=False),
        sa.Column("translated_by_agent_id", sa.String, nullable=False),
        sa.Column("method", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("source_event", sa.String, nullable=False, server_default="initial"),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
    )
    op.create_index("ix_translation_unit_versions_unit_id", "translation_unit_versions", ["unit_id"])

    op.create_table(
        "deployment_records",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("translation_unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("context", sa.String, nullable=False),
        sa.Column("location", sa.String, nullable=False),
        sa.Column("deployed_at", sa.DateTime, nullable=False),
        sa.Column("deployed_by", sa.String, nullable=True),
        sa.Column("version", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("retired_at", sa.DateTime, nullable=True),
        sa.Column("prov_entity_id", sa.String, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_deployment_records_translation_unit_id", "deployment_records", ["translation_unit_id"])

    op.create_table(
        "provenance_bundles",
        sa.Column("bundle_id", sa.String, primary_key=True),
        sa.Column("translation_unit_id", sa.String, sa.ForeignKey("translation_units.id"), nullable=False),
        sa.Column("xliff_document_id", sa.String, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.create_index("ix_provenance_bundles_translation_unit_id", "provenance_bundles", ["translation_unit_id"])

    op.create_table(
        "provenance_entities",
        # entity_id is deterministic per TranslationUnit (e.g.
        # "entity:translation:{unit_id}"), reused across every bundle
        # rebuilt over that unit's lifetime — so it can only be unique
        # *within* a bundle, not globally. Primary key is a synthetic
        # autoincrement instead.
        sa.Column("pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("bundle_id", sa.String, sa.ForeignKey("provenance_bundles.bundle_id"), nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("was_generated_by", sa.String, nullable=True),
        sa.Column("was_derived_from", sa.String, nullable=True),
        sa.Column("was_attributed_to", sa.String, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=False),
        sa.Column("invalidated_at", sa.DateTime, nullable=True),
        sa.Column("attributes", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_provenance_entities_bundle_id", "provenance_entities", ["bundle_id"])
    op.create_index("ix_provenance_entities_entity_id", "provenance_entities", ["entity_id"])

    op.create_table(
        "provenance_activities",
        # Same rationale as provenance_entities.pk above — activity_id repeats
        # across bundles rebuilt for the same unit.
        sa.Column("pk", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("activity_id", sa.String, nullable=False),
        sa.Column("bundle_id", sa.String, sa.ForeignKey("provenance_bundles.bundle_id"), nullable=False),
        sa.Column("activity_type", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("used_entity_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_provenance_activities_bundle_id", "provenance_activities", ["bundle_id"])
    op.create_index("ix_provenance_activities_activity_id", "provenance_activities", ["activity_id"])

    op.create_table(
        "provenance_relations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bundle_id", sa.String, sa.ForeignKey("provenance_bundles.bundle_id"), nullable=False),
        sa.Column("rel_type", sa.String, nullable=False),
        sa.Column("data", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_provenance_relations_bundle_id", "provenance_relations", ["bundle_id"])

    op.create_table(
        "xliff_documents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("xml_content", sa.Text, nullable=False),
        sa.Column("translation_unit_id", sa.String, nullable=True),
        sa.Column("project_id", sa.String, nullable=True),
        sa.Column("direction", sa.String, nullable=False, server_default="out"),
        sa.Column("source_system", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("xliff_documents")
    op.drop_table("provenance_relations")
    op.drop_table("provenance_activities")
    op.drop_table("provenance_entities")
    op.drop_table("provenance_bundles")
    op.drop_table("deployment_records")
    op.drop_table("translation_unit_versions")
    op.drop_table("translation_units")
    op.drop_table("translation_projects")
    op.drop_table("provenance_agents")
