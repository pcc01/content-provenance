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

from typing import Any, Dict, Optional

from app.core.database import get_db
from app.core.integrations.factory import get_tms_integration
from app.models.schemas import IngestDirection


async def send_unit_for_review(
    unit_id: str,
    *,
    provider: Optional[str] = None,
    include_mt_draft: bool = True,
    include_quality_note: bool = True,
) -> Dict[str, Any]:
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

    suggestion_added = False
    if include_mt_draft and unit.target_text:
        await integration.add_suggestion(
            string_id=string_id, language=unit.target_language, text=unit.target_text,
        )
        suggestion_added = True

    comment_added = False
    if include_quality_note:
        note = await _quality_note(db, unit)
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
