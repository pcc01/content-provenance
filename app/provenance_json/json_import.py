"""
JSON Provenance Document Import — the JSON peer of app/xliff/xliff_import.py
(app/api/json_export.py + the shared IngestEvent ledger are the "leaving"
half, see app/api/json_import.py for where both directions get logged).

Ingests an externally supplied JSON document — this system's own extensive
export, or a bare/minimal JSON file (see json_service.parse_json_document
for exactly how lenient that acceptance is) — and creates/updates
TranslationUnit + version history rows, exactly like xliff_import.py does
for XLIFF. Any "provenance"/"deployments"/"version_history" the parsed
unit carries is ignored: provenance is always rebuilt fresh server-side,
so importing a plain/minimal JSON file and then exporting the same unit
back out (GET /api/v1/json/{unit_id}) is precisely how a minimal file
becomes "the more extensive version with the provenance metadata."

If a parsed unit carries no recognizable translation_method (common for a
minimal/foreign file), method defaults to HUMAN — never fabricate an
AI-authorship claim for content of unknown origin, same rule
xliff_import.py follows.
"""

from datetime import datetime
from typing import List, Optional

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record
from app.models.schemas import TranslationMethod, TranslationStatus, TranslationUnit
from app.provenance_json.json_service import parse_json_document

# A foreign JSON file might reuse XLIFF's segment-state vocabulary instead
# of this system's own TranslationStatus values — accepted as a fallback,
# same spirit as translation_method's alias tolerance in json_service.
_XLIFF_STATE_TO_STATUS = {
    "initial": TranslationStatus.PENDING,
    "translated": TranslationStatus.COMPLETED,
    "reviewed": TranslationStatus.REVIEWED,
    "final": TranslationStatus.PUBLISHED,
}


def _resolve_status(raw: Optional[str], default: TranslationStatus) -> TranslationStatus:
    if not raw:
        return default
    try:
        return TranslationStatus(raw)
    except ValueError:
        return _XLIFF_STATE_TO_STATUS.get(raw, default)


async def import_provenance_json(json_content: str, source_system: str) -> List[TranslationUnit]:
    db = get_db()
    parsed_units = parse_json_document(json_content)

    external_agent = await db.get_or_create_agent(
        name=f"external:{source_system}",
        agent_type="SoftwareAgent",
        organization=source_system,
        metadata={"role": "json_import_source"},
    )

    imported: List[TranslationUnit] = []
    for parsed in parsed_units:
        method_raw = parsed.get("translation_method")
        try:
            method = TranslationMethod(method_raw) if method_raw else None
        except ValueError:
            method = None
        method_inferred = method is not None
        method = method or TranslationMethod.HUMAN

        unit_id = parsed.get("id")
        existing = await db.get_translation_unit(unit_id) if unit_id else None

        if existing:
            existing.target_text = parsed.get("target_text") or existing.target_text
            existing.status = _resolve_status(parsed.get("status"), existing.status)
            await db.save_translation_unit(existing, version_source_event="import")
            # Rebuild provenance now that a new version may exist — otherwise
            # GET /provenance/{id} (and GET /json/{id}) keep serving the
            # bundle from before this import.
            deps = await db.get_deployments_for_unit(existing.id)
            prov_record = await build_provenance_record(existing, deps)
            await db.save_provenance_record(prov_record)
            imported.append(existing)
            continue

        unit_kwargs = dict(
            source_id=unit_id or "",
            source_text=parsed.get("source_text") or "",
            source_language=parsed.get("source_language") or "en",
            target_text=parsed.get("target_text"),
            target_language=parsed.get("target_language") or "",
            translation_method=method,
            translated_by_agent_id=external_agent.id,
            translated_at=datetime.utcnow(),
            status=_resolve_status(parsed.get("status"), TranslationStatus.COMPLETED),
            confidence_score=parsed.get("confidence_score"),
            quality_score=parsed.get("quality_score"),
            metadata={
                **(parsed.get("metadata") or {}),
                "import_source": source_system,
                "method_inferred": method_inferred,
            },
        )
        # Preserve the original unit id when present so re-importing a
        # document this system itself exported updates the same unit
        # instead of creating a duplicate.
        if unit_id:
            unit_kwargs["id"] = unit_id

        unit = TranslationUnit(**unit_kwargs)
        await db.save_translation_unit(unit, version_source_event="import")
        prov_record = await build_provenance_record(unit, deployments=[])
        unit.prov_entity_id = prov_record.entities[1].id if len(prov_record.entities) > 1 else None
        await db.save_translation_unit(unit, version_source_event="import")
        await db.save_provenance_record(prov_record)
        imported.append(unit)

    return imported
