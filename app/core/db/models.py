"""
SQLAlchemy ORM models — the Postgres-backed schema behind app/models/schemas.py's
Pydantic models. Table shape mirrors the Pydantic fields field-for-field so the
repository layer (app/core/db/repository.py) can convert between the two with
straightforward attribute copies.

Note: pydantic's `metadata: Dict[str, Any]` field is mapped to a column named
"metadata" but a Python attribute named `meta` — `metadata` is reserved on
DeclarativeBase (it's the schema MetaData object).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _agent_id() -> str:
    return f"agent:{uuid.uuid4()}"


def _bundle_id() -> str:
    return f"bundle:{uuid.uuid4()}"


# ─── Agents ─────────────────────────────────────────────────────────────────

class AgentRow(Base):
    __tablename__ = "provenance_agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_agent_id)
    name: Mapped[str] = mapped_column(String, index=True)
    agent_type: Mapped[str] = mapped_column(String)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


# ─── Projects ───────────────────────────────────────────────────────────────

class TranslationProjectRow(Base):
    __tablename__ = "translation_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_language: Mapped[str] = mapped_column(String)
    target_languages: Mapped[list] = mapped_column(JSON, default=list)
    context: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    translation_units: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


# ─── Translation units + version history ───────────────────────────────────

class TranslationUnitRow(Base):
    __tablename__ = "translation_units"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String)
    source_text: Mapped[str] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(String)
    target_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_language: Mapped[str] = mapped_column(String)

    translation_method: Mapped[str] = mapped_column(String)
    translated_by_agent_id: Mapped[str] = mapped_column(String)
    translated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by_agent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")
    prov_entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("translation_projects.id"), nullable=True, index=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class TranslationUnitVersionRow(Base):
    """Full edit history for a unit's target_text — one row per version.
    source_event distinguishes how the version came to be: initial | redrive |
    human_edit | import (Phase 2/3 write into this; Phase 1 only reads/writes
    the "initial" version so PROV's future wasRevisionOf chain has something
    to walk)."""
    __tablename__ = "translation_unit_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(
        String, ForeignKey("translation_units.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    target_text: Mapped[str] = mapped_column(Text)
    translated_by_agent_id: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_event: Mapped[str] = mapped_column(String, default="initial")
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ─── Deployments ────────────────────────────────────────────────────────────

class DeploymentRecordRow(Base):
    __tablename__ = "deployment_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    translation_unit_id: Mapped[str] = mapped_column(
        String, ForeignKey("translation_units.id"), index=True
    )
    context: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    deployed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deployed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    prov_entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


# ─── W3C PROV-DM (normalized) ───────────────────────────────────────────────

class ProvenanceBundleRow(Base):
    __tablename__ = "provenance_bundles"

    bundle_id: Mapped[str] = mapped_column(String, primary_key=True, default=_bundle_id)
    # No FK: this is a polymorphic subject id — a TranslationUnit id (the
    # original/common case) OR an ImageTranslationUnit id (Phase 4) share this
    # same provenance-bundle mechanism, so it can't point at one specific table.
    translation_unit_id: Mapped[str] = mapped_column(String, index=True)
    xliff_document_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProvenanceEntityRow(Base):
    """entity_id (e.g. "activity:translate:{unit_id}") is deterministic per
    TranslationUnit, NOT per bundle — prov_builder.py rebuilds a fresh bundle
    (new random bundle_id) on every mutation (deploy, review, ...) but reuses
    the same entity/activity ids across those rebuilds. So entity_id can only
    be unique *within* a bundle, not globally — the real primary key has to
    be synthetic, or a second rebuild collides with the first bundle's rows."""
    __tablename__ = "provenance_entities"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    bundle_id: Mapped[str] = mapped_column(
        String, ForeignKey("provenance_bundles.bundle_id"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String)
    was_generated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    was_derived_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    was_attributed_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class ProvenanceActivityRow(Base):
    """Same rationale as ProvenanceEntityRow.pk — activity_id is deterministic
    per unit, not globally unique across the bundles rebuilt over its lifetime."""
    __tablename__ = "provenance_activities"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[str] = mapped_column(String, index=True)
    bundle_id: Mapped[str] = mapped_column(
        String, ForeignKey("provenance_bundles.bundle_id"), index=True
    )
    activity_type: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    agent_id: Mapped[str] = mapped_column(String)
    used_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ProvenanceRelationRow(Base):
    """Relations are heterogeneous dicts keyed by `type` (wasGeneratedBy,
    wasDerivedFrom, ...). Rather than a table-per-relation-type, store the
    whole dict as JSON and duplicate `type` into `rel_type` for filtering —
    matches how app/core/prov_builder.py already treats relations as
    untyped dicts, so no reshaping is needed at the boundary."""
    __tablename__ = "provenance_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[str] = mapped_column(
        String, ForeignKey("provenance_bundles.bundle_id"), index=True
    )
    rel_type: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


# ─── XLIFF documents (everything entering/leaving the system) ─────────────

class XliffDocumentRow(Base):
    __tablename__ = "xliff_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    xml_content: Mapped[str] = mapped_column(Text)
    translation_unit_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    direction: Mapped[str] = mapped_column(String, default="out")  # in | out
    source_system: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityScoreRow(Base):
    __tablename__ = "quality_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(String, ForeignKey("translation_units.id"), index=True)
    version_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scorer: Mapped[str] = mapped_column(String)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RedriveRunRow(Base):
    __tablename__ = "redrive_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String, default="pending")
    threshold: Mapped[float] = mapped_column(Float)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_provider: Mapped[str] = mapped_column(String)
    redrive_provider: Mapped[str] = mapped_column(String)
    require_human_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class RedriveRunItemRow(Base):
    __tablename__ = "redrive_run_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("redrive_runs.id"), index=True)
    unit_id: Mapped[str] = mapped_column(String, index=True)
    before_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    after_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proposed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ProviderUsageLedgerRow(Base):
    """Lightweight per-provider usage counter (chars sent through redrive),
    one row per (provider, period). period is either a "YYYY-MM" string for
    scope="month" or the literal "lifetime" for scope="lifetime" — mirrors
    peripateticware's mt_fallback.py UsageLedger concept, DB-backed instead
    of a JSON file since Phase 1 already put this system on Postgres."""
    __tablename__ = "provider_usage_ledger"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String)
    scope: Mapped[str] = mapped_column(String, default="month")
    limit_chars: Mapped[int] = mapped_column(Integer)
    used_chars: Mapped[int] = mapped_column(Integer, default=0)


class ImageAssetRow(Base):
    __tablename__ = "image_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String)  # context | translatable
    storage_path: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    checksum: Mapped[str] = mapped_column(String, index=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    alt_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ImageTranslationUnitRow(Base):
    __tablename__ = "image_translation_units"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_image_id: Mapped[str] = mapped_column(String, ForeignKey("image_assets.id"), index=True)
    target_image_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("image_assets.id"), nullable=True)
    source_language: Mapped[str] = mapped_column(String)
    target_language: Mapped[str] = mapped_column(String)

    translation_method: Mapped[str] = mapped_column(String)
    translated_by_agent_id: Mapped[str] = mapped_column(String)
    translated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by_agent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")

    overlay_text_unit_ids: Mapped[list] = mapped_column(JSON, default=list)
    prov_entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ImageContextLinkRow(Base):
    __tablename__ = "image_context_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    image_id: Mapped[str] = mapped_column(String, ForeignKey("image_assets.id"), index=True)
    translation_unit_id: Mapped[str] = mapped_column(
        String, ForeignKey("translation_units.id"), index=True
    )
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewNoteRow(Base):
    __tablename__ = "review_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(String, index=True)
    author: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class DocumentRow(Base):
    """A Phase 7a imported text/Markdown document. Its segments are ordinary
    TranslationUnitRow rows carrying {"document_id": id, "position": N} in
    their own metadata column — see app/models/schemas.py's Document
    docstring for why there's no separate segments/join table."""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    original_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format: Mapped[str] = mapped_column(String)
    source_language: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class IngestEventRow(Base):
    """One row per XLIFF document entering or leaving the system — separate
    from XliffDocumentRow (which stores the artifact itself) so the ledger
    stays queryable/summarizable even for documents that were never cached
    (e.g. project-level exports don't currently persist their XML)."""
    __tablename__ = "ingest_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    direction: Mapped[str] = mapped_column(String)  # in | out
    format: Mapped[str] = mapped_column(String, default="xliff")
    source_system: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    xliff_document_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
