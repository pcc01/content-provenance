"""
Translations API endpoints
POST /api/v1/translations/          - Submit a new translation
GET  /api/v1/translations/          - List all translations
GET  /api/v1/translations/{id}      - Get a specific translation
POST /api/v1/translations/{id}/deploy - Record a deployment
GET  /api/v1/translations/stats     - Aggregated statistics
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
import uuid

from app.models.schemas import (
    TranslateRequest, TranslateResponse, TranslationUnit, DeploymentRecord,
    TranslationMethod, TranslationStatus, DeploymentContext
)
from app.core.database import get_db
from app.core.prov_builder import build_provenance_record, to_prov_json
from app.core.haystack_pipeline import index_translation_unit
from app.core.translation_backends import get_translation_backend
from app.xliff.xliff_service import build_single_unit_xliff

router = APIRouter()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=TranslateResponse, status_code=201)
async def create_translation(request: TranslateRequest):
    """
    Submit content for translation with full provenance tracking.
    
    Workflow:
    1. Determine/create translator agent
    2. Perform translation (AI or record human translation)
    3. Create XLIFF 2.0 document
    4. Build W3C PROV-DM provenance record
    5. Index in Haystack for semantic search
    6. Optionally record deployment context
    """
    db = get_db()
    now = datetime.utcnow()
    
    # ── 1. Resolve agent ──────────────────────────────────────────────────────
    if request.method == TranslationMethod.HUMAN:
        agent_name = request.translator_name or "Human Translator"
        agent = await db.get_or_create_agent(
            name=agent_name,
            agent_type="Person",
            metadata={"role": "human_translator"}
        )
    elif request.method == TranslationMethod.HYBRID:
        agent_name = request.translator_name or "claude-3-7-sonnet"
        ai_agent = await db.get_or_create_agent(
            name="claude-3-7-sonnet",
            agent_type="SoftwareAgent",
            model_version="claude-3-7-sonnet-20250219",
            organization="Anthropic",
        )
        # Registers the human post-editor as a known agent too (side effect
        # of get_or_create_agent) even though only the AI agent is the
        # primary one returned below — a hybrid translation involved both.
        await db.get_or_create_agent(
            name=request.translator_name or "Post-Editor",
            agent_type="Person",
        )
        agent = ai_agent  # primary agent
    else:
        agent = await db.get_or_create_agent(
            name="claude-3-7-sonnet",
            agent_type="SoftwareAgent",
            model_version="claude-3-7-sonnet-20250219",
            organization="Anthropic",
        )
    
    # ── 2. Translate ──────────────────────────────────────────────────────────
    if request.method in (TranslationMethod.AI, TranslationMethod.HYBRID):
        backend = get_translation_backend()
        translated_text, confidence = await backend.translate(
            request.source_text,
            request.source_language,
            request.target_language,
            domain=request.domain,
        )
    else:
        # Human translation — text would be supplied by a TMS integration
        translated_text = f"[Awaiting human translation] {request.source_text}"
        confidence = 1.0  # Human translations assumed correct
    
    # ── 3. Build TranslationUnit ──────────────────────────────────────────────
    source_id = str(uuid.uuid4())
    
    unit = TranslationUnit(
        source_id=source_id,
        source_text=request.source_text,
        source_language=request.source_language,
        target_text=translated_text,
        target_language=request.target_language,
        translation_method=request.method,
        translated_by_agent_id=agent.id,
        translated_at=now,
        confidence_score=confidence,
        quality_score=None,
        status=TranslationStatus.COMPLETED if request.method == TranslationMethod.AI else TranslationStatus.PENDING,
        metadata={
            "domain": request.domain,
            "project_id": request.project_id,
            "context": request.context.value,
        }
    )
    await db.save_translation_unit(unit)

    # ── 4. Record deployment if location provided ─────────────────────────────
    deployments = []
    if request.deployment_location:
        dep = DeploymentRecord(
            translation_unit_id=unit.id,
            context=request.context,
            location=request.deployment_location,
            deployed_at=now,
        )
        await db.save_deployment_record(dep)
        deployments.append(dep)

    # ── 5. Build provenance record ────────────────────────────────────────────
    prov_record = await build_provenance_record(unit, deployments)
    unit.prov_entity_id = prov_record.entities[1].id if len(prov_record.entities) > 1 else None
    await db.save_translation_unit(unit)
    await db.save_provenance_record(prov_record)

    # Serialize to PROV-JSON
    prov_json = to_prov_json(prov_record)
    await db.save_prov_json(prov_record.bundle_id, prov_json)

    # ── 6. Generate XLIFF document ────────────────────────────────────────────
    xliff_doc_id = unit.id
    xliff_xml = build_single_unit_xliff(unit)
    await db.save_xliff(xliff_doc_id, xliff_xml, translation_unit_id=unit.id, direction="out")
    
    # ── 7. Index in Haystack ──────────────────────────────────────────────────
    await index_translation_unit(unit, deployments)
    
    return TranslateResponse(
        translation_unit_id=unit.id,
        source_text=unit.source_text,
        translated_text=translated_text,
        source_language=unit.source_language,
        target_language=unit.target_language,
        method=unit.translation_method,
        confidence_score=confidence,
        provenance_record_id=prov_record.bundle_id,
        xliff_document_id=xliff_doc_id,
        status=unit.status,
        translated_at=now,
    )


@router.get("/stats")
async def get_stats():
    """Return aggregated statistics about all translations."""
    db = get_db()
    return await db.get_stats()


@router.get("/", response_model=List[dict])
async def list_translations(
    source_language: Optional[str] = Query(None),
    target_language: Optional[str] = Query(None),
    method: Optional[TranslationMethod] = Query(None),
    status: Optional[TranslationStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List all translation units with optional filters."""
    db = get_db()
    units = await db.list_translation_units(source_language, target_language, method, status, limit)
    return [unit.model_dump() for unit in units]


@router.get("/batch")
async def get_translations_batch(ids: str = Query(..., description="Comma-separated translation unit ids")):
    """Bulk lookup for the review overlay SDK — fetches quality/status for a
    whole page's worth of segments in one call instead of one request per
    highlighted element."""
    db = get_db()
    unit_ids = [i.strip() for i in ids.split(",") if i.strip()]
    results = []
    for unit_id in unit_ids:
        unit = await db.get_translation_unit(unit_id)
        if not unit:
            continue
        latest_score = await db.get_latest_quality_score(unit_id)
        results.append({
            **unit.model_dump(),
            "latest_score": latest_score.score if latest_score else None,
            "latest_score_reasons": latest_score.reasons if latest_score else [],
        })
    return results


@router.get("/{unit_id}")
async def get_translation(unit_id: str):
    """Get a specific translation unit by ID."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    return unit.model_dump()


@router.get("/{unit_id}/versions")
async def get_translation_versions(unit_id: str):
    """Full edit history for a unit — the review UI's version timeline."""
    db = get_db()
    if not await db.get_translation_unit(unit_id):
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    versions = await db.list_translation_unit_versions(unit_id)
    return [v.model_dump() for v in versions]


@router.post("/{unit_id}/deploy")
async def record_deployment(
    unit_id: str,
    context: DeploymentContext,
    location: str,
    deployed_by: Optional[str] = None,
    version: Optional[str] = None,
):
    """Record a new deployment location for a translation."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    dep = DeploymentRecord(
        translation_unit_id=unit_id,
        context=context,
        location=location,
        deployed_at=datetime.utcnow(),
        deployed_by=deployed_by,
        version=version,
    )
    await db.save_deployment_record(dep)

    # Update provenance
    all_deps = await db.get_deployments_for_unit(unit_id)
    prov_record = await build_provenance_record(unit, all_deps)
    await db.save_provenance_record(prov_record)
    await db.save_prov_json(prov_record.bundle_id, to_prov_json(prov_record))
    await db.delete_xliff(unit_id)  # cached export is now stale — force regeneration

    # Re-index
    await index_translation_unit(unit, all_deps)
    
    return {"deployment_id": dep.id, "message": "Deployment recorded successfully"}


@router.put("/{unit_id}/review")
async def mark_reviewed(
    unit_id: str,
    reviewer_name: str,
    quality_score: Optional[float] = None,
):
    """Mark a translation as reviewed by a human."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    reviewer = await db.get_or_create_agent(reviewer_name, "Person")
    unit.reviewed_by_agent_id = reviewer.id
    unit.reviewed_at = datetime.utcnow()
    unit.quality_score = quality_score
    unit.status = TranslationStatus.REVIEWED
    await db.save_translation_unit(unit)

    # Rebuild provenance
    deps = await db.get_deployments_for_unit(unit_id)
    prov_record = await build_provenance_record(unit, deps)
    await db.save_provenance_record(prov_record)
    await db.delete_xliff(unit_id)  # cached export is now stale — force regeneration
    
    return {"message": "Review recorded", "reviewed_by": reviewer_name, "status": unit.status}
