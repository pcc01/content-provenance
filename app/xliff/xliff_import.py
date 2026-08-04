"""
XLIFF 2.0 Import — the "entering the system" half of the provenance ledger
(app/api/xliff_export.py + the IngestEvent log are the "leaving" half, see
app/api/xliff_import.py for where both directions get logged).

Ingests an externally supplied XLIFF 2.0 document (from a TMS/CAT tool, a
different content-provenance instance, or a re-upload of this system's own
prior export) and creates/updates TranslationUnit + version history rows so
imported content is tracked exactly like natively-created content.

If a parsed <unit> carries no embedded W3C PROV metadata (common — most
external tools don't embed PROV the way this system's own xliff_service.py
does), a minimal provenance stub is synthesized: an "external:{source_system}"
agent, method defaulted to HUMAN (never fabricate an AI-authorship claim for
content of unknown origin) — rather than failing the import outright.
"""

from datetime import datetime
from typing import List

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.models.schemas import TranslationMethod, TranslationStatus, TranslationUnit
from app.xliff.xliff_service import parse_xliff_document

_STATE_TO_STATUS = {
    "initial": TranslationStatus.PENDING,
    "translated": TranslationStatus.COMPLETED,
    "reviewed": TranslationStatus.REVIEWED,
    "final": TranslationStatus.PUBLISHED,
}


async def import_xliff(xml_content: str, source_system: str) -> List[TranslationUnit]:
    db = get_db()
    parsed_units = parse_xliff_document(xml_content)
    if not parsed_units:
        raise ValueError("No <unit> elements found in the supplied XLIFF document")

    external_agent = await db.get_or_create_agent(
        name=f"external:{source_system}",
        agent_type="SoftwareAgent",
        organization=source_system,
        metadata={"role": "xliff_import_source"},
    )

    imported: List[TranslationUnit] = []
    for parsed in parsed_units:
        # This system's own exports carry a "unit:translationMethod" note
        # (see xliff_service._build_unit) even though parse_xliff_document
        # doesn't extract it into a named field — it's still there in
        # raw_notes, so a re-import of our own content recovers the real
        # method instead of falling back to the "unknown origin" default.
        method_note = parsed["raw_notes"].get("unit:translationMethod", {}).get("value")
        try:
            method = TranslationMethod(method_note) if method_note else None
        except ValueError:
            method = None
        method_inferred = method is not None
        method = method or TranslationMethod.HUMAN

        existing = await db.get_translation_unit(parsed["id"]) if parsed["id"] else None

        if existing:
            existing.target_text = parsed["target"] or existing.target_text
            existing.status = _STATE_TO_STATUS.get(parsed["state"], existing.status)
            await db.save_translation_unit(existing, version_source_event="import")
            # Rebuild provenance now that a new version may exist — otherwise
            # GET /provenance/{id} keeps serving the bundle from before this
            # import (same fallback-rebuild gap record_deployment/mark_reviewed
            # in app/api/translations.py already have to guard against).
            deps = await db.get_deployments_for_unit(existing.id)
            prov_record = await build_provenance_record(existing, deps)
            await db.save_provenance_record(prov_record)
            await db.delete_xliff(existing.id)
            imported.append(existing)
            continue

        unit_kwargs = dict(
            source_id=parsed["id"] or "",
            source_text=parsed["source"] or "",
            source_language=parsed["source_language"] or "en",
            target_text=parsed["target"],
            target_language=parsed["target_language"] or "",
            translation_method=method,
            translated_by_agent_id=external_agent.id,
            translated_at=datetime.utcnow(),
            status=_STATE_TO_STATUS.get(parsed["state"], TranslationStatus.COMPLETED),
            metadata={"import_source": source_system, "method_inferred": method_inferred},
        )
        # Preserve the original unit id when present so re-importing a
        # document this system itself exported updates the same unit
        # instead of creating a duplicate.
        if parsed["id"]:
            unit_kwargs["id"] = parsed["id"]

        unit = TranslationUnit(**unit_kwargs)
        await db.save_translation_unit(unit, version_source_event="import")
        prov_record = await build_provenance_record(unit, deployments=[])
        unit.prov_entity_id = prov_record.entities[1].id if len(prov_record.entities) > 1 else None
        await db.save_translation_unit(unit, version_source_event="import")
        await db.save_provenance_record(prov_record)
        imported.append(unit)

    return imported
