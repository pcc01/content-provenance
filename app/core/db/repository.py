"""
PostgresRepository — replaces app/core/database.py's InMemoryDatabase.

Exposes the SAME public method names the in-memory store had
(save_translation_unit, get_translation_unit, list_translation_units,
save_provenance_record, get_or_create_agent, ...) so app/api/*.py and
app/core/prov_builder.py only need `await` added at call sites, not a
rewrite. Two additions beyond the original contract:

  get_agent(agent_id)             — prov_builder.py used to reach into
                                     InMemoryDatabase.agents (a raw dict)
                                     directly; Postgres has no equivalent
                                     public dict, so this is the proper
                                     accessor for that same lookup.
  save_translation_unit_version / list_translation_unit_versions
                                   — new; Phase 2/3 build on top of these
                                     for edit history and redrive, but the
                                     "initial" version is written here in
                                     Phase 1 so that history exists from
                                     the very first translation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.db.models import (
    AgentRow, DeploymentRecordRow, DocumentRow, ImageAssetRow, ImageContextLinkRow,
    ImageTranslationUnitRow, IngestEventRow, PageSnapshotRow, ProviderUsageLedgerRow,
    ProvenanceActivityRow, ProvenanceBundleRow, ProvenanceEntityRow,
    ProvenanceRelationRow, QualityScoreRow, RedriveRunItemRow, RedriveRunRow,
    ReviewNoteRow, TranslationProjectRow, TranslationUnitRow,
    TranslationUnitVersionRow, XliffDocumentRow,
)
from app.models.schemas import (
    DeploymentContext, DeploymentRecord, Document, DocumentFormat, ImageAsset,
    ImageAssetKind, ImageContextLink, ImageTranslationUnit, IngestDirection,
    IngestEvent, PageSnapshot, ProvenanceActivity, ProvenanceAgent, ProvenanceEntity,
    ProvenanceRecord, QualityScore, RedriveOutcome, RedriveRun, RedriveRunItem,
    RedriveRunStatus, ReviewNote, ScoreError, TranslationMethod,
    TranslationProject, TranslationStatus, TranslationUnit, TranslationUnitVersion,
)


class PostgresRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    # ── Translation Units ───────────────────────────────────────────────

    async def save_translation_unit(
        self, unit: TranslationUnit, version_source_event: str = "human_edit",
        version_note: Optional[str] = None,
    ) -> TranslationUnit:
        """version_source_event/version_note only apply to non-initial
        versions — the very first version for a unit is always tagged
        "initial" regardless of what's passed. Callers with more specific
        knowledge than a plain edit (xliff_import.py -> "import", the redrive
        engine -> "redrive") should pass that instead of the "human_edit"
        default."""
        async with self._session_factory() as session:
            row = await session.get(TranslationUnitRow, unit.id)
            if row is None:
                row = TranslationUnitRow(id=unit.id)
                session.add(row)
            _unit_to_row(unit, row)
            await session.commit()

            # Keep a version-history row in sync with target_text so Phase
            # 2's wasRevisionOf chain and Phase 5's version timeline have
            # something to read from the very first translation onward.
            existing = (
                await session.execute(
                    select(TranslationUnitVersionRow)
                    .where(TranslationUnitVersionRow.unit_id == unit.id)
                    .order_by(TranslationUnitVersionRow.version_number.desc())
                )
            ).scalars().first()
            if existing is None or existing.target_text != (unit.target_text or ""):
                next_version = (existing.version_number + 1) if existing else 1
                session.add(TranslationUnitVersionRow(
                    unit_id=unit.id,
                    version_number=next_version,
                    target_text=unit.target_text or "",
                    translated_by_agent_id=unit.translated_by_agent_id,
                    method=unit.translation_method.value,
                    created_at=unit.translated_at or datetime.utcnow(),
                    source_event="initial" if next_version == 1 else version_source_event,
                    quality_score=unit.quality_score,
                    note=version_note if next_version > 1 else None,
                ))
                await session.commit()
            return unit

    async def get_translation_unit(self, unit_id: str) -> Optional[TranslationUnit]:
        async with self._session_factory() as session:
            row = await session.get(TranslationUnitRow, unit_id)
            return _row_to_unit(row) if row else None

    async def list_translation_units(
        self,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        method: Optional[TranslationMethod] = None,
        status: Optional[TranslationStatus] = None,
        limit: int = 50,
    ) -> List[TranslationUnit]:
        async with self._session_factory() as session:
            stmt = select(TranslationUnitRow)
            if source_language:
                stmt = stmt.where(TranslationUnitRow.source_language == source_language)
            if target_language:
                stmt = stmt.where(TranslationUnitRow.target_language == target_language)
            if method:
                stmt = stmt.where(TranslationUnitRow.translation_method == method.value)
            if status:
                stmt = stmt.where(TranslationUnitRow.status == status.value)
            # Without an ORDER BY, which rows a LIMIT keeps is undefined —
            # harmless until a table has more rows than the limit, at which
            # point results become nondeterministic (surfaced by test
            # flakiness once enough units accumulated in a shared test DB).
            stmt = stmt.order_by(TranslationUnitRow.translated_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_unit(r) for r in rows]

    async def get_translation_unit_by_source_id(
        self, source_id: str, target_language: str,
    ) -> Optional[TranslationUnit]:
        """Phase 8's harvest-and-match: source_id carries a stable content
        hash for page-harvested units, so re-fetching the same page finds
        the existing unit instead of creating a duplicate."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(TranslationUnitRow)
                    .where(
                        TranslationUnitRow.source_id == source_id,
                        TranslationUnitRow.target_language == target_language,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _row_to_unit(row) if row else None

    # ── Translation Unit Versions ───────────────────────────────────────

    async def save_translation_unit_version(
        self,
        unit_id: str,
        target_text: str,
        translated_by_agent_id: str,
        method: TranslationMethod,
        source_event: str = "human_edit",
        quality_score: Optional[float] = None,
        note: Optional[str] = None,
    ) -> int:
        """Explicit version write (used by Phase 2 import + Phase 3 redrive,
        which need to record a version without going through
        save_translation_unit's diff-on-target_text heuristic). Returns the
        new version_number."""
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(TranslationUnitVersionRow)
                    .where(TranslationUnitVersionRow.unit_id == unit_id)
                    .order_by(TranslationUnitVersionRow.version_number.desc())
                )
            ).scalars().first()
            next_version = (existing.version_number + 1) if existing else 1
            session.add(TranslationUnitVersionRow(
                unit_id=unit_id,
                version_number=next_version,
                target_text=target_text,
                translated_by_agent_id=translated_by_agent_id,
                method=method.value,
                created_at=datetime.utcnow(),
                source_event=source_event,
                quality_score=quality_score,
                note=note,
            ))
            await session.commit()
            return next_version

    async def list_translation_unit_versions(self, unit_id: str) -> List[TranslationUnitVersion]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(TranslationUnitVersionRow)
                    .where(TranslationUnitVersionRow.unit_id == unit_id)
                    .order_by(TranslationUnitVersionRow.version_number.asc())
                )
            ).scalars().all()
            return [
                TranslationUnitVersion(
                    id=r.id, unit_id=r.unit_id, version_number=r.version_number,
                    target_text=r.target_text, translated_by_agent_id=r.translated_by_agent_id,
                    method=TranslationMethod(r.method), created_at=r.created_at,
                    source_event=r.source_event, quality_score=r.quality_score, note=r.note,
                )
                for r in rows
            ]

    async def list_translation_unit_versions_for_units(
        self, unit_ids: List[str],
    ) -> Dict[str, List[TranslationUnitVersion]]:
        """Batch form of list_translation_unit_versions — Phase 9's
        time-travel needs every version of every unit on a page (can be
        150+ units), so one query beats one-per-unit."""
        result: Dict[str, List[TranslationUnitVersion]] = {uid: [] for uid in unit_ids}
        if not unit_ids:
            return result
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(TranslationUnitVersionRow)
                    .where(TranslationUnitVersionRow.unit_id.in_(unit_ids))
                    .order_by(TranslationUnitVersionRow.version_number.asc())
                )
            ).scalars().all()
            for r in rows:
                result.setdefault(r.unit_id, []).append(TranslationUnitVersion(
                    id=r.id, unit_id=r.unit_id, version_number=r.version_number,
                    target_text=r.target_text, translated_by_agent_id=r.translated_by_agent_id,
                    method=TranslationMethod(r.method), created_at=r.created_at,
                    source_event=r.source_event, quality_score=r.quality_score, note=r.note,
                ))
            return result

    async def list_version_timestamps(self, unit_ids: List[str]) -> List[datetime]:
        """Distinct points in time at which something on a page's harvested
        units changed — Phase 9's timeline/"commit list"."""
        if not unit_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(TranslationUnitVersionRow.created_at)
                    .where(TranslationUnitVersionRow.unit_id.in_(unit_ids))
                    .distinct()
                    .order_by(TranslationUnitVersionRow.created_at.asc())
                )
            ).scalars().all()
            return list(rows)

    # ── Provenance Records ──────────────────────────────────────────────

    async def save_provenance_record(self, record: ProvenanceRecord) -> ProvenanceRecord:
        async with self._session_factory() as session:
            bundle = await session.get(ProvenanceBundleRow, record.bundle_id)
            if bundle is None:
                bundle = ProvenanceBundleRow(bundle_id=record.bundle_id)
                session.add(bundle)
            bundle.translation_unit_id = record.translation_unit_id
            bundle.xliff_document_id = record.xliff_document_id
            bundle.generated_at = record.generated_at
            bundle.summary = record.summary
            await session.flush()

            # Replace entities/activities/relations wholesale — simpler and
            # safer than diffing, and a bundle is rebuilt in full every time
            # (see prov_builder.build_provenance_record).
            for model, col in (
                (ProvenanceEntityRow, ProvenanceEntityRow.bundle_id),
                (ProvenanceActivityRow, ProvenanceActivityRow.bundle_id),
                (ProvenanceRelationRow, ProvenanceRelationRow.bundle_id),
            ):
                existing = (await session.execute(select(model).where(col == record.bundle_id))).scalars().all()
                for e in existing:
                    await session.delete(e)
            await session.flush()

            for entity in record.entities:
                session.add(ProvenanceEntityRow(
                    entity_id=entity.id, bundle_id=record.bundle_id, entity_type=entity.entity_type,
                    was_generated_by=entity.was_generated_by, was_derived_from=entity.was_derived_from,
                    was_attributed_to=entity.was_attributed_to, generated_at=entity.generated_at,
                    invalidated_at=entity.invalidated_at, attributes=entity.attributes,
                ))
            for act in record.activities:
                session.add(ProvenanceActivityRow(
                    activity_id=act.id, bundle_id=record.bundle_id, activity_type=act.activity_type,
                    started_at=act.started_at, ended_at=act.ended_at, agent_id=act.agent_id,
                    used_entity_ids=act.used_entity_ids, meta=act.metadata,
                ))
            for rel in record.relations:
                session.add(ProvenanceRelationRow(
                    bundle_id=record.bundle_id, rel_type=rel.get("type", ""), data=rel,
                ))
            await session.commit()
            return record

    async def get_provenance_by_unit(self, unit_id: str) -> Optional[ProvenanceRecord]:
        async with self._session_factory() as session:
            bundle = (
                await session.execute(
                    select(ProvenanceBundleRow)
                    .where(ProvenanceBundleRow.translation_unit_id == unit_id)
                    .order_by(ProvenanceBundleRow.generated_at.desc())
                )
            ).scalars().first()
            if bundle is None:
                return None
            return await self._load_bundle(session, bundle)

    async def get_provenance_by_bundle(self, bundle_id: str) -> Optional[ProvenanceRecord]:
        async with self._session_factory() as session:
            bundle = await session.get(ProvenanceBundleRow, bundle_id)
            if bundle is None:
                return None
            return await self._load_bundle(session, bundle)

    async def _load_bundle(self, session, bundle: ProvenanceBundleRow) -> ProvenanceRecord:
        entities = (
            await session.execute(select(ProvenanceEntityRow).where(ProvenanceEntityRow.bundle_id == bundle.bundle_id))
        ).scalars().all()
        activities = (
            await session.execute(select(ProvenanceActivityRow).where(ProvenanceActivityRow.bundle_id == bundle.bundle_id))
        ).scalars().all()
        relations = (
            await session.execute(select(ProvenanceRelationRow).where(ProvenanceRelationRow.bundle_id == bundle.bundle_id))
        ).scalars().all()

        agent_ids = {a.agent_id for a in activities} | {e.was_attributed_to for e in entities if e.was_attributed_to}
        agents = []
        for agent_id in agent_ids:
            agent_row = await session.get(AgentRow, agent_id)
            agents.append(_row_to_agent(agent_row) if agent_row else ProvenanceAgent(
                id=agent_id, name="Unknown Agent", agent_type="SoftwareAgent",
            ))

        return ProvenanceRecord(
            bundle_id=bundle.bundle_id,
            translation_unit_id=bundle.translation_unit_id,
            xliff_document_id=bundle.xliff_document_id,
            generated_at=bundle.generated_at,
            summary=bundle.summary,
            entities=[_row_to_entity(e) for e in entities],
            activities=[_row_to_activity(a) for a in activities],
            agents=agents,
            relations=[r.data for r in relations],
        )

    # ── Deployment Records ──────────────────────────────────────────────

    async def save_deployment_record(self, record: DeploymentRecord) -> DeploymentRecord:
        async with self._session_factory() as session:
            row = DeploymentRecordRow(
                id=record.id, translation_unit_id=record.translation_unit_id,
                context=record.context.value, location=record.location,
                deployed_at=record.deployed_at, deployed_by=record.deployed_by,
                version=record.version, is_active=record.is_active,
                retired_at=record.retired_at, prov_entity_id=record.prov_entity_id,
                meta=record.metadata,
            )
            session.add(row)
            await session.commit()
            return record

    async def get_deployments_for_unit(self, unit_id: str) -> List[DeploymentRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(DeploymentRecordRow).where(DeploymentRecordRow.translation_unit_id == unit_id)
                )
            ).scalars().all()
            return [_row_to_deployment(r) for r in rows]

    # ── Projects ─────────────────────────────────────────────────────────

    async def save_project(self, project: TranslationProject) -> TranslationProject:
        async with self._session_factory() as session:
            row = await session.get(TranslationProjectRow, project.id)
            if row is None:
                row = TranslationProjectRow(id=project.id)
                session.add(row)
            row.name = project.name
            row.description = project.description
            row.source_language = project.source_language
            row.target_languages = project.target_languages
            row.context = project.context.value
            row.created_at = project.created_at
            row.created_by = project.created_by
            row.translation_units = project.translation_units
            row.meta = project.metadata
            await session.commit()
            return project

    async def get_project(self, project_id: str) -> Optional[TranslationProject]:
        async with self._session_factory() as session:
            row = await session.get(TranslationProjectRow, project_id)
            if row is None:
                return None
            return TranslationProject(
                id=row.id, name=row.name, description=row.description,
                source_language=row.source_language, target_languages=row.target_languages,
                context=DeploymentContext(row.context), created_at=row.created_at,
                created_by=row.created_by, translation_units=row.translation_units,
                metadata=row.meta,
            )

    # ── Agents ───────────────────────────────────────────────────────────

    async def save_agent(self, agent: ProvenanceAgent) -> ProvenanceAgent:
        async with self._session_factory() as session:
            row = await session.get(AgentRow, agent.id)
            if row is None:
                row = AgentRow(id=agent.id)
                session.add(row)
            row.name = agent.name
            row.agent_type = agent.agent_type
            row.model_version = agent.model_version
            row.organization = agent.organization
            row.meta = agent.metadata
            await session.commit()
            return agent

    async def get_agent(self, agent_id: str) -> Optional[ProvenanceAgent]:
        async with self._session_factory() as session:
            row = await session.get(AgentRow, agent_id)
            return _row_to_agent(row) if row else None

    async def get_or_create_agent(self, name: str, agent_type: str, **kwargs) -> ProvenanceAgent:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(AgentRow).where(AgentRow.name == name, AgentRow.agent_type == agent_type)
                )
            ).scalars().first()
            if row:
                return _row_to_agent(row)

        agent = ProvenanceAgent(name=name, agent_type=agent_type, **kwargs)
        return await self.save_agent(agent)

    # ── XLIFF Documents ──────────────────────────────────────────────────

    async def save_xliff(
        self, doc_id: str, xml_content: str,
        translation_unit_id: Optional[str] = None, project_id: Optional[str] = None,
        direction: str = "out", source_system: Optional[str] = None,
    ) -> str:
        async with self._session_factory() as session:
            row = await session.get(XliffDocumentRow, doc_id)
            if row is None:
                row = XliffDocumentRow(id=doc_id)
                session.add(row)
            row.xml_content = xml_content
            row.translation_unit_id = translation_unit_id
            row.project_id = project_id
            row.direction = direction
            row.source_system = source_system
            await session.commit()
            return doc_id

    async def get_xliff(self, doc_id: str) -> Optional[str]:
        async with self._session_factory() as session:
            row = await session.get(XliffDocumentRow, doc_id)
            return row.xml_content if row else None

    async def delete_xliff(self, doc_id: str) -> None:
        """Invalidates a cached XLIFF document so the next export/preview
        regenerates it from current data. Must be called wherever a unit's
        provenance is rebuilt after the initial translation (deploy, review,
        import, and Phase 3's redrive) — otherwise export/preview keep
        serving whatever was cached at creation time, silently wrong after
        any of those mutations."""
        async with self._session_factory() as session:
            row = await session.get(XliffDocumentRow, doc_id)
            if row:
                await session.delete(row)
                await session.commit()

    # ── Image Assets ─────────────────────────────────────────────────────

    async def save_image_asset(self, asset: ImageAsset) -> ImageAsset:
        async with self._session_factory() as session:
            session.add(ImageAssetRow(
                id=asset.id, kind=asset.kind.value, storage_path=asset.storage_path,
                content_type=asset.content_type, checksum=asset.checksum,
                original_filename=asset.original_filename, alt_text=asset.alt_text,
                uploaded_at=asset.uploaded_at, uploaded_by=asset.uploaded_by, meta=asset.metadata,
            ))
            await session.commit()
        return asset

    async def get_image_asset(self, image_id: str) -> Optional[ImageAsset]:
        async with self._session_factory() as session:
            row = await session.get(ImageAssetRow, image_id)
            return _row_to_image_asset(row) if row else None

    async def save_image_translation_unit(self, itu: ImageTranslationUnit) -> ImageTranslationUnit:
        async with self._session_factory() as session:
            row = await session.get(ImageTranslationUnitRow, itu.id)
            if row is None:
                row = ImageTranslationUnitRow(id=itu.id)
                session.add(row)
            row.source_image_id = itu.source_image_id
            row.target_image_id = itu.target_image_id
            row.source_language = itu.source_language
            row.target_language = itu.target_language
            row.translation_method = itu.translation_method.value
            row.translated_by_agent_id = itu.translated_by_agent_id
            row.translated_at = itu.translated_at
            row.reviewed_by_agent_id = itu.reviewed_by_agent_id
            row.reviewed_at = itu.reviewed_at
            row.confidence_score = itu.confidence_score
            row.quality_score = itu.quality_score
            row.status = itu.status.value
            row.overlay_text_unit_ids = itu.overlay_text_unit_ids
            row.prov_entity_id = itu.prov_entity_id
            row.meta = itu.metadata
            await session.commit()
        return itu

    async def get_image_translation_unit(self, itu_id: str) -> Optional[ImageTranslationUnit]:
        async with self._session_factory() as session:
            row = await session.get(ImageTranslationUnitRow, itu_id)
            return _row_to_image_translation_unit(row) if row else None

    async def list_image_translation_units_for_source(self, source_image_id: str) -> List[ImageTranslationUnit]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ImageTranslationUnitRow).where(
                        ImageTranslationUnitRow.source_image_id == source_image_id
                    )
                )
            ).scalars().all()
            return [_row_to_image_translation_unit(r) for r in rows]

    async def save_image_context_link(self, link: ImageContextLink) -> ImageContextLink:
        async with self._session_factory() as session:
            session.add(ImageContextLinkRow(
                id=link.id, image_id=link.image_id, translation_unit_id=link.translation_unit_id,
                note=link.note, created_at=link.created_at,
            ))
            await session.commit()
        return link

    async def list_context_images_for_unit(self, translation_unit_id: str) -> List[ImageAsset]:
        async with self._session_factory() as session:
            links = (
                await session.execute(
                    select(ImageContextLinkRow).where(
                        ImageContextLinkRow.translation_unit_id == translation_unit_id
                    )
                )
            ).scalars().all()
            assets = []
            for link in links:
                row = await session.get(ImageAssetRow, link.image_id)
                if row:
                    assets.append(_row_to_image_asset(row))
            return assets

    # ── Review Notes ─────────────────────────────────────────────────────

    async def save_review_note(self, note: ReviewNote) -> ReviewNote:
        async with self._session_factory() as session:
            session.add(ReviewNoteRow(
                id=note.id, unit_id=note.unit_id, page_url=note.page_url,
                target_language=note.target_language, author=note.author, body=note.body,
                created_at=note.created_at, resolved=note.resolved, parent_id=note.parent_id,
            ))
            await session.commit()
        return note

    async def list_review_notes(self, unit_id: str) -> List[ReviewNote]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ReviewNoteRow).where(ReviewNoteRow.unit_id == unit_id)
                    .order_by(ReviewNoteRow.created_at.asc())
                )
            ).scalars().all()
            return [_row_to_review_note(r) for r in rows]

    async def list_page_notes(self, page_url: str, target_language: str) -> List[ReviewNote]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ReviewNoteRow)
                    .where(
                        ReviewNoteRow.page_url == page_url,
                        ReviewNoteRow.target_language == target_language,
                    )
                    .order_by(ReviewNoteRow.created_at.asc())
                )
            ).scalars().all()
            return [_row_to_review_note(r) for r in rows]

    async def resolve_review_note(self, note_id: str, resolved: bool = True) -> Optional[ReviewNote]:
        async with self._session_factory() as session:
            row = await session.get(ReviewNoteRow, note_id)
            if not row:
                return None
            row.resolved = resolved
            await session.commit()
            return _row_to_review_note(row)

    # ── Ingest Events (everything entering/leaving the system) ─────────────

    async def log_ingest_event(
        self, direction: IngestDirection, format: str = "xliff",
        source_system: Optional[str] = None, xliff_document_id: Optional[str] = None,
        unit_count: int = 0,
    ) -> IngestEvent:
        event = IngestEvent(
            direction=direction, format=format, source_system=source_system,
            xliff_document_id=xliff_document_id, unit_count=unit_count,
        )
        async with self._session_factory() as session:
            session.add(IngestEventRow(
                id=event.id, direction=event.direction.value, format=event.format,
                source_system=event.source_system, xliff_document_id=event.xliff_document_id,
                unit_count=event.unit_count, created_at=event.created_at,
            ))
            await session.commit()
        return event

    async def list_ingest_events(self, limit: int = 100) -> List[IngestEvent]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(IngestEventRow).order_by(IngestEventRow.created_at.desc()).limit(limit)
                )
            ).scalars().all()
            return [
                IngestEvent(
                    id=r.id, direction=IngestDirection(r.direction), format=r.format,
                    source_system=r.source_system, xliff_document_id=r.xliff_document_id,
                    unit_count=r.unit_count, created_at=r.created_at,
                )
                for r in rows
            ]

    # ── Documents (Phase 7a: plain text/Markdown in-context review) ────────

    async def save_document(self, document: Document) -> Document:
        async with self._session_factory() as session:
            session.add(DocumentRow(
                id=document.id, title=document.title,
                original_filename=document.original_filename, format=document.format.value,
                source_language=document.source_language, created_at=document.created_at,
                uploaded_by=document.uploaded_by, meta=document.metadata,
            ))
            await session.commit()
        return document

    async def get_document(self, document_id: str) -> Optional[Document]:
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
            return _row_to_document(row) if row else None

    async def list_translation_units_for_document(
        self, document_id: str, target_language: Optional[str] = None,
    ) -> List[TranslationUnit]:
        """Segments for a document, in reading order. Filters in Python on
        metadata->document_id rather than a JSON-path query — this repository
        has no dedicated segments table (see Document's docstring), and a
        full scan is fine at this system's current scale."""
        async with self._session_factory() as session:
            stmt = select(TranslationUnitRow)
            if target_language:
                stmt = stmt.where(TranslationUnitRow.target_language == target_language)
            rows = (await session.execute(stmt)).scalars().all()
            units = [
                _row_to_unit(r) for r in rows if r.meta.get("document_id") == document_id
            ]
            units.sort(key=lambda u: u.metadata.get("position", 0))
            return units

    # ── Page Snapshots (Phase 8: non-cooperative page review) ──────────────

    async def save_page_snapshot(self, snapshot: PageSnapshot) -> PageSnapshot:
        async with self._session_factory() as session:
            session.add(PageSnapshotRow(
                id=snapshot.id, url=snapshot.url, target_language=snapshot.target_language,
                html=snapshot.html, harvested_unit_ids=snapshot.harvested_unit_ids,
                fetched_at=snapshot.fetched_at,
            ))
            await session.commit()
        return snapshot

    async def get_latest_page_snapshot(
        self, url: str, target_language: str,
    ) -> Optional[PageSnapshot]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PageSnapshotRow)
                    .where(PageSnapshotRow.url == url, PageSnapshotRow.target_language == target_language)
                    .order_by(PageSnapshotRow.fetched_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _row_to_page_snapshot(row) if row else None

    async def list_page_snapshots(self, url: str, target_language: str) -> List[PageSnapshot]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(PageSnapshotRow)
                    .where(PageSnapshotRow.url == url, PageSnapshotRow.target_language == target_language)
                    .order_by(PageSnapshotRow.fetched_at.asc())
                )
            ).scalars().all()
            return [_row_to_page_snapshot(r) for r in rows]

    # ── PROV-JSON ────────────────────────────────────────────────────────
    # Not persisted separately — it's a pure function of a ProvenanceRecord
    # (see app.core.prov_builder.to_prov_json), so recomputing on a cache
    # miss is cheap and avoids a redundant cache-invalidation table.

    async def save_prov_json(self, bundle_id: str, prov_doc: Dict) -> None:
        return None

    async def get_prov_json(self, bundle_id: str) -> Optional[Dict]:
        return None

    # ── Quality Scores ───────────────────────────────────────────────────

    async def save_quality_score(self, result: QualityScore) -> QualityScore:
        async with self._session_factory() as session:
            session.add(QualityScoreRow(
                id=result.id, unit_id=result.unit_id, version_id=result.version_id,
                score=result.score, scorer=result.scorer,
                reasons=result.reasons, errors=[e.model_dump() for e in result.errors],
                raw_response=result.raw_response, needs_review=result.needs_review,
                scored_at=result.scored_at,
            ))
            await session.commit()
        return result

    async def get_latest_quality_score(self, unit_id: str) -> Optional[QualityScore]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(QualityScoreRow)
                    .where(QualityScoreRow.unit_id == unit_id)
                    .order_by(QualityScoreRow.scored_at.desc())
                )
            ).scalars().first()
            return _row_to_quality_score(row) if row else None

    async def list_units_by_scope(self, scope: Dict[str, Any]) -> List[TranslationUnit]:
        """scope keys: unit_ids (explicit list, takes precedence over
        everything else), source_language, target_language, status, limit."""
        async with self._session_factory() as session:
            if scope.get("unit_ids"):
                rows = []
                for uid in scope["unit_ids"]:
                    row = await session.get(TranslationUnitRow, uid)
                    if row:
                        rows.append(row)
                return [_row_to_unit(r) for r in rows]

            stmt = select(TranslationUnitRow)
            if scope.get("source_language"):
                stmt = stmt.where(TranslationUnitRow.source_language == scope["source_language"])
            if scope.get("target_language"):
                stmt = stmt.where(TranslationUnitRow.target_language == scope["target_language"])
            if scope.get("status"):
                stmt = stmt.where(TranslationUnitRow.status == scope["status"])
            if scope.get("project_id"):
                stmt = stmt.where(TranslationUnitRow.project_id == scope["project_id"])
            stmt = stmt.limit(scope.get("limit", 500))
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_unit(r) for r in rows]

    # ── Redrive Runs ─────────────────────────────────────────────────────

    async def create_redrive_run(self, run: RedriveRun) -> RedriveRun:
        async with self._session_factory() as session:
            session.add(RedriveRunRow(
                id=run.id, status=run.status.value, threshold=run.threshold,
                scope=run.scope, scoring_provider=run.scoring_provider,
                redrive_provider=run.redrive_provider,
                require_human_approval=run.require_human_approval,
                triggered_by=run.triggered_by,
                started_at=run.started_at, finished_at=run.finished_at, summary=run.summary,
            ))
            await session.commit()
        return run

    async def update_redrive_run(
        self, run_id: str, status: Optional[RedriveRunStatus] = None,
        finished_at: Optional[datetime] = None, summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(RedriveRunRow, run_id)
            if not row:
                return
            if status is not None:
                row.status = status.value
            if finished_at is not None:
                row.finished_at = finished_at
            if summary is not None:
                row.summary = summary
            await session.commit()

    async def add_redrive_run_item(self, item: RedriveRunItem) -> RedriveRunItem:
        async with self._session_factory() as session:
            session.add(RedriveRunItemRow(
                id=item.id, run_id=item.run_id, unit_id=item.unit_id,
                before_score=item.before_score, after_score=item.after_score,
                outcome=item.outcome.value, detail=item.detail,
                proposed_text=item.proposed_text, approved_by=item.approved_by,
                approved_at=item.approved_at,
            ))
            await session.commit()
        return item

    async def get_redrive_run_item(self, item_id: str) -> Optional[RedriveRunItem]:
        async with self._session_factory() as session:
            row = await session.get(RedriveRunItemRow, item_id)
            return _row_to_redrive_run_item(row) if row else None

    async def update_redrive_run_item(
        self, item_id: str, outcome: Optional[RedriveOutcome] = None,
        after_score: Optional[float] = None, detail: Optional[str] = None,
        approved_by: Optional[str] = None, approved_at: Optional[datetime] = None,
    ) -> Optional[RedriveRunItem]:
        """Used by the human-in-the-loop approve/reject endpoints to
        transition a PENDING_APPROVAL item once a reviewer decides."""
        async with self._session_factory() as session:
            row = await session.get(RedriveRunItemRow, item_id)
            if not row:
                return None
            if outcome is not None:
                row.outcome = outcome.value
            if after_score is not None:
                row.after_score = after_score
            if detail is not None:
                row.detail = detail
            if approved_by is not None:
                row.approved_by = approved_by
            if approved_at is not None:
                row.approved_at = approved_at
            await session.commit()
            return _row_to_redrive_run_item(row)

    async def get_redrive_run(self, run_id: str) -> Optional[RedriveRun]:
        async with self._session_factory() as session:
            row = await session.get(RedriveRunRow, run_id)
            if not row:
                return None
            items = (
                await session.execute(select(RedriveRunItemRow).where(RedriveRunItemRow.run_id == run_id))
            ).scalars().all()
            return RedriveRun(
                id=row.id, status=RedriveRunStatus(row.status), threshold=row.threshold,
                scope=row.scope, scoring_provider=row.scoring_provider,
                redrive_provider=row.redrive_provider,
                require_human_approval=row.require_human_approval,
                triggered_by=row.triggered_by,
                started_at=row.started_at, finished_at=row.finished_at, summary=row.summary,
                items=[_row_to_redrive_run_item(i) for i in items],
            )

    async def list_pending_redrive_items_for_units(self, unit_ids: List[str]) -> List[RedriveRunItem]:
        """Phase 10's editor view: every PENDING_APPROVAL item touching any
        of a page's harvested units, regardless of which (possibly ad-hoc,
        possibly batch) run created it."""
        if not unit_ids:
            return []
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(RedriveRunItemRow).where(
                        RedriveRunItemRow.unit_id.in_(unit_ids),
                        RedriveRunItemRow.outcome == RedriveOutcome.PENDING_APPROVAL.value,
                    )
                )
            ).scalars().all()
            return [_row_to_redrive_run_item(r) for r in rows]

    # ── Provider Usage Ledger ────────────────────────────────────────────

    async def get_or_create_ledger_row(
        self, provider: str, period: str, scope: str, limit_chars: int,
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ProviderUsageLedgerRow).where(
                        ProviderUsageLedgerRow.provider == provider,
                        ProviderUsageLedgerRow.period == period,
                    )
                )
            ).scalars().first()
            if row is None:
                row = ProviderUsageLedgerRow(
                    provider=provider, period=period, scope=scope, limit_chars=limit_chars,
                )
                session.add(row)
                await session.commit()
            return {"provider": row.provider, "period": row.period, "scope": row.scope,
                    "limit_chars": row.limit_chars, "used_chars": row.used_chars}

    async def record_usage(self, provider: str, period: str, chars: int) -> None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ProviderUsageLedgerRow).where(
                        ProviderUsageLedgerRow.provider == provider,
                        ProviderUsageLedgerRow.period == period,
                    )
                )
            ).scalars().first()
            if row is None:
                return
            row.used_chars += chars
            await session.commit()

    # ── Stats ────────────────────────────────────────────────────────────

    async def get_stats(self) -> Dict[str, Any]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(TranslationUnitRow))).scalars().all()
            deployments = (await session.execute(select(DeploymentRecordRow))).scalars().all()
            projects = (await session.execute(select(TranslationProjectRow))).scalars().all()
            agents = (await session.execute(select(AgentRow))).scalars().all()
            return {
                "total_translations": len(rows),
                "by_method": {
                    "ai": sum(1 for u in rows if u.translation_method == "ai"),
                    "human": sum(1 for u in rows if u.translation_method == "human"),
                    "hybrid": sum(1 for u in rows if u.translation_method == "hybrid"),
                },
                "by_status": {
                    s.value: sum(1 for u in rows if u.status == s.value)
                    for s in TranslationStatus
                },
                "total_deployments": len(deployments),
                "total_projects": len(projects),
                "total_agents": len(agents),
            }


# ─── Row <-> Pydantic mappers ────────────────────────────────────────────

def _unit_to_row(unit: TranslationUnit, row: TranslationUnitRow) -> None:
    row.source_id = unit.source_id
    row.source_text = unit.source_text
    row.source_language = unit.source_language
    row.target_text = unit.target_text
    row.target_language = unit.target_language
    row.translation_method = unit.translation_method.value
    row.translated_by_agent_id = unit.translated_by_agent_id
    row.translated_at = unit.translated_at
    row.reviewed_by_agent_id = unit.reviewed_by_agent_id
    row.reviewed_at = unit.reviewed_at
    row.confidence_score = unit.confidence_score
    row.quality_score = unit.quality_score
    row.status = unit.status.value
    row.prov_entity_id = unit.prov_entity_id
    row.meta = unit.metadata


def _row_to_unit(row: TranslationUnitRow) -> TranslationUnit:
    return TranslationUnit(
        id=row.id, source_id=row.source_id, source_text=row.source_text,
        source_language=row.source_language, target_text=row.target_text,
        target_language=row.target_language,
        translation_method=TranslationMethod(row.translation_method),
        translated_by_agent_id=row.translated_by_agent_id, translated_at=row.translated_at,
        reviewed_by_agent_id=row.reviewed_by_agent_id, reviewed_at=row.reviewed_at,
        confidence_score=row.confidence_score, quality_score=row.quality_score,
        status=TranslationStatus(row.status), prov_entity_id=row.prov_entity_id,
        metadata=row.meta,
    )


def _row_to_agent(row: AgentRow) -> ProvenanceAgent:
    return ProvenanceAgent(
        id=row.id, name=row.name, agent_type=row.agent_type,
        model_version=row.model_version, organization=row.organization, metadata=row.meta,
    )


def _row_to_entity(row: ProvenanceEntityRow) -> ProvenanceEntity:
    return ProvenanceEntity(
        id=row.entity_id, entity_type=row.entity_type, was_generated_by=row.was_generated_by,
        was_derived_from=row.was_derived_from, was_attributed_to=row.was_attributed_to,
        generated_at=row.generated_at, invalidated_at=row.invalidated_at, attributes=row.attributes,
    )


def _row_to_activity(row: ProvenanceActivityRow) -> ProvenanceActivity:
    return ProvenanceActivity(
        id=row.activity_id, activity_type=row.activity_type, started_at=row.started_at,
        ended_at=row.ended_at, agent_id=row.agent_id, used_entity_ids=row.used_entity_ids,
        metadata=row.meta,
    )


def _row_to_redrive_run_item(row: RedriveRunItemRow) -> RedriveRunItem:
    return RedriveRunItem(
        id=row.id, run_id=row.run_id, unit_id=row.unit_id,
        before_score=row.before_score, after_score=row.after_score,
        outcome=RedriveOutcome(row.outcome), detail=row.detail,
        proposed_text=row.proposed_text, approved_by=row.approved_by, approved_at=row.approved_at,
    )


def _row_to_quality_score(row: QualityScoreRow) -> QualityScore:
    return QualityScore(
        id=row.id, unit_id=row.unit_id, version_id=row.version_id, score=row.score,
        scorer=row.scorer, reasons=row.reasons,
        errors=[ScoreError(**e) for e in row.errors],
        raw_response=row.raw_response, needs_review=row.needs_review, scored_at=row.scored_at,
    )


def _row_to_review_note(row: ReviewNoteRow) -> ReviewNote:
    return ReviewNote(
        id=row.id, unit_id=row.unit_id, page_url=row.page_url, target_language=row.target_language,
        author=row.author, body=row.body, created_at=row.created_at, resolved=row.resolved,
        parent_id=row.parent_id,
    )


def _row_to_page_snapshot(row: PageSnapshotRow) -> PageSnapshot:
    return PageSnapshot(
        id=row.id, url=row.url, target_language=row.target_language, html=row.html,
        harvested_unit_ids=row.harvested_unit_ids, fetched_at=row.fetched_at,
    )


def _row_to_document(row: DocumentRow) -> Document:
    return Document(
        id=row.id, title=row.title, original_filename=row.original_filename,
        format=DocumentFormat(row.format), source_language=row.source_language,
        created_at=row.created_at, uploaded_by=row.uploaded_by, metadata=row.meta,
    )


def _row_to_image_asset(row: ImageAssetRow) -> ImageAsset:
    return ImageAsset(
        id=row.id, kind=ImageAssetKind(row.kind), storage_path=row.storage_path,
        content_type=row.content_type, checksum=row.checksum,
        original_filename=row.original_filename, alt_text=row.alt_text,
        uploaded_at=row.uploaded_at, uploaded_by=row.uploaded_by, metadata=row.meta,
    )


def _row_to_image_translation_unit(row: ImageTranslationUnitRow) -> ImageTranslationUnit:
    return ImageTranslationUnit(
        id=row.id, source_image_id=row.source_image_id, target_image_id=row.target_image_id,
        source_language=row.source_language, target_language=row.target_language,
        translation_method=TranslationMethod(row.translation_method),
        translated_by_agent_id=row.translated_by_agent_id, translated_at=row.translated_at,
        reviewed_by_agent_id=row.reviewed_by_agent_id, reviewed_at=row.reviewed_at,
        confidence_score=row.confidence_score, quality_score=row.quality_score,
        status=TranslationStatus(row.status), overlay_text_unit_ids=row.overlay_text_unit_ids,
        prov_entity_id=row.prov_entity_id, metadata=row.meta,
    )


def _row_to_deployment(row: DeploymentRecordRow) -> DeploymentRecord:
    return DeploymentRecord(
        id=row.id, translation_unit_id=row.translation_unit_id,
        context=DeploymentContext(row.context), location=row.location,
        deployed_at=row.deployed_at, deployed_by=row.deployed_by, version=row.version,
        is_active=row.is_active, retired_at=row.retired_at, prov_entity_id=row.prov_entity_id,
        metadata=row.meta,
    )
