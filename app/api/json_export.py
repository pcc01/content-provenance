"""JSON Provenance Document Export API — the JSON peer of app/api/xliff_export.py."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.database import get_db
from app.models.schemas import IngestDirection
from app.provenance_json.json_service import build_json_document, build_single_unit_json

router = APIRouter()


@router.get("/{unit_id}", response_class=Response)
async def export_json_unit(unit_id: str):
    """Export a single translation unit as a JSON provenance document."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    prov_records = {}
    prov = await db.get_provenance_by_unit(unit_id)
    if prov:
        prov_records[unit_id] = prov

    deps = {unit_id: await db.get_deployments_for_unit(unit_id)}
    versions = {unit_id: await db.list_translation_unit_versions(unit_id)}

    doc = build_json_document(
        units=[unit],
        provenance_records=prov_records,
        deployments=deps,
        versions=versions,
        project_name=f"Export {unit_id[:8]}",
        doc_id=unit_id,
    )
    await db.log_ingest_event(
        direction=IngestDirection.OUT, format="json", xliff_document_id=unit_id, unit_count=1,
    )

    return Response(
        content=json.dumps(doc, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="translation-{unit_id[:8]}.json"'},
    )


@router.get("/project/{project_id}", response_class=Response)
async def export_json_project(project_id: str):
    """Export all translations in a project as a single JSON provenance document."""
    db = get_db()
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    units = [await db.get_translation_unit(uid) for uid in project.translation_units]
    units = [u for u in units if u]
    if not units:
        raise HTTPException(status_code=404, detail="No translation units found in project")

    prov_records = {u.id: await db.get_provenance_by_unit(u.id) for u in units}
    prov_records = {k: v for k, v in prov_records.items() if v}
    deps = {u.id: await db.get_deployments_for_unit(u.id) for u in units}
    versions = {u.id: await db.list_translation_unit_versions(u.id) for u in units}

    doc = build_json_document(
        units=units,
        provenance_records=prov_records,
        deployments=deps,
        versions=versions,
        project_name=project.name,
        doc_id=project_id,
    )
    await db.log_ingest_event(
        direction=IngestDirection.OUT, format="json", xliff_document_id=project_id, unit_count=len(units),
    )

    return Response(
        content=json.dumps(doc, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="project-{project.name}.json"'},
    )


@router.get("/{unit_id}/preview")
async def preview_json(unit_id: str):
    """Preview the JSON provenance document without triggering a download."""
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    return build_single_unit_json(unit)
