"""TMS push/pull orchestration — the business logic behind app/api/tms.py,
the workflow-level peer of app/core/cms_service.py.

send_unit_for_review pushes a source string into the TMS with an optional
MT draft (as a suggestion the reviewer accepts/edits) and an optional
quality note (score + flags, as a comment) — then logs an outbound
ingest event. The string is keyed by the TranslationUnit id so the
approved translation can find its way home.

apply_approved_translation (Phase 2) closes the loop: a webhook / poll
result becomes a new HYBRID, reviewed version of the unit, with provenance
rebuilt and any open redrive item for it resolved.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from app.core.database import get_db
from app.core.integrations.base import TMSApprovalEvent
from app.core.integrations.factory import get_tms_integration
from app.core.prov_builder import build_provenance_record
from app.models.schemas import IngestDirection, TranslationMethod, TranslationStatus


async def send_unit_for_review(
    unit_id: str,
    *,
    provider: Optional[str] = None,
    include_mt_draft: bool = True,
    include_quality_note: bool = True,
    mt_draft: Optional[str] = None,
    quality_note: Optional[str] = None,
) -> Dict[str, Any]:
    """`mt_draft` / `quality_note` override what would otherwise be read from
    the unit — used by the redrive engine to send the *fresh* draft (not the
    unit's still-unchanged target) and a note built from the report item."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise LookupError(f"Translation unit {unit_id} not found")

    integration = get_tms_integration(provider)  # ValueError if unconfigured

    context = f"unit {unit.id}"
    doc_id = unit.metadata.get("document_id")
    if doc_id:
        context = f"doc {doc_id} · position {unit.metadata.get('position')}"

    res = await integration.upsert_source_string(
        key=unit.id, text=unit.source_text, context=context,
    )
    string_id = res["string_id"]

    draft = mt_draft if mt_draft is not None else unit.target_text
    suggestion_added = False
    if include_mt_draft and draft:
        await integration.add_suggestion(
            string_id=string_id, language=unit.target_language, text=draft,
        )
        suggestion_added = True

    comment_added = False
    if include_quality_note:
        note = quality_note if quality_note is not None else await _quality_note(db, unit)
        if note:
            await integration.add_comment(string_id=string_id, text=note)
            comment_added = True

    await db.log_ingest_event(
        direction=IngestDirection.OUT, format="crowdin",
        source_system=integration.provider, unit_count=1,
    )

    return {
        "unit_id": unit.id,
        "provider": integration.provider,
        "string_id": string_id,
        "created": bool(res.get("created", False)),
        "suggestion_added": suggestion_added,
        "comment_added": comment_added,
    }


async def _quality_note(db, unit) -> str:
    parts = [f"AI-drafted ({unit.translation_method.value})"]
    score = await db.get_latest_quality_score(unit.id)
    if score is not None:
        parts.append(f"quality score {score.score}")
        if score.reasons:
            parts.append("flags: " + "; ".join(score.reasons[:5]))
    parts.append("via Content Provenance")
    return " — ".join(parts)


async def apply_approved_translation(
    event: TMSApprovalEvent, *, provider: Optional[str] = None,
) -> Dict[str, Any]:
    """A TMS-approved translation (from a webhook or a poll) becomes a new
    HYBRID, reviewed version of the unit: provenance rebuilt, XLIFF cache
    busted, and any open redrive item for the unit closed. `event.key` is
    the TranslationUnit id we set as the source string's identifier."""
    db = get_db()
    unit = await db.get_translation_unit(event.key)
    if unit is None:
        return {"applied": False, "unit_id": None, "detail": f"no translation unit for key {event.key!r}"}
    if event.approved_text == unit.target_text:
        return {"applied": False, "unit_id": unit.id, "detail": "approved text already matches the current target"}

    reviewer_name = event.translator or "Crowdin reviewer"
    reviewer = await db.get_or_create_agent(reviewer_name, "Person")

    unit.target_text = event.approved_text
    unit.translation_method = TranslationMethod.HYBRID
    unit.status = TranslationStatus.REVIEWED
    unit.reviewed_by_agent_id = reviewer.id
    unit.reviewed_at = datetime.utcnow()
    await db.save_translation_unit(
        unit, version_source_event="tms_review",
        version_note=f"Approved in {(provider or 'crowdin').title()} by {reviewer_name}",
    )

    deps = await db.get_deployments_for_unit(unit.id)
    await db.save_provenance_record(await build_provenance_record(unit, deps))
    await db.delete_xliff(unit.id)

    resolved = await db.resolve_tms_redrive_items(unit.id, "approved in Crowdin", reviewer_name)
    await db.log_ingest_event(
        direction=IngestDirection.IN, format="crowdin",
        source_system=provider or "crowdin", unit_count=1,
    )
    return {
        "applied": True, "unit_id": unit.id,
        "detail": f"applied; {resolved} open redrive item(s) resolved",
    }


async def apply_from_poll(unit_id: str, *, provider: Optional[str] = None) -> Dict[str, Any]:
    """Polling fallback for deployments with no public webhook URL: ask the
    TMS for the unit's current approved translation and apply it if there is
    one and it differs."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if unit is None:
        raise LookupError(f"Translation unit {unit_id} not found")

    integration = get_tms_integration(provider)
    text = await integration.fetch_approved_translation(key=unit.id, language=unit.target_language)
    if not text:
        return {"applied": False, "unit_id": unit.id, "detail": "no approved translation in the TMS yet"}

    return await apply_approved_translation(
        TMSApprovalEvent(key=unit.id, language=unit.target_language, approved_text=text),
        provider=integration.provider,
    )
