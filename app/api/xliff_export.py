"""XLIFF 2.0 Export API endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.database import get_db
from app.models.schemas import IngestDirection
from app.xliff.xliff_service import build_xliff_document

router = APIRouter()


@router.get("/{unit_id}", response_class=Response)
async def export_xliff_unit(unit_id: str):
    """Export a single translation unit as XLIFF 2.0 XML."""
    db = get_db()

    # Check cache first
    cached = await db.get_xliff(unit_id)
    if cached:
        await db.log_ingest_event(
            direction=IngestDirection.OUT, format="xliff", xliff_document_id=unit_id, unit_count=1,
        )
        return Response(content=cached, media_type="application/xliff+xml",
                       headers={"Content-Disposition": f'attachment; filename="translation-{unit_id[:8]}.xliff"'})

    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")

    prov_records = {}
    prov = await db.get_provenance_by_unit(unit_id)
    if prov:
        prov_records[unit_id] = prov

    deps = {unit_id: await db.get_deployments_for_unit(unit_id)}
    versions = {unit_id: await db.list_translation_unit_versions(unit_id)}

    xliff_xml = build_xliff_document(
        units=[unit],
        provenance_records=prov_records,
        deployments=deps,
        versions=versions,
        project_name=f"Export {unit_id[:8]}",
        doc_id=unit_id,
    )
    await db.save_xliff(unit_id, xliff_xml, translation_unit_id=unit_id, direction="out")
    await db.log_ingest_event(
        direction=IngestDirection.OUT, format="xliff", xliff_document_id=unit_id, unit_count=1,
    )

    return Response(
        content=xliff_xml,
        media_type="application/xliff+xml",
        headers={"Content-Disposition": f'attachment; filename="translation-{unit_id[:8]}.xliff"'}
    )


@router.get("/project/{project_id}", response_class=Response)
async def export_xliff_project(project_id: str):
    """Export all translations in a project as a single XLIFF 2.0 document."""
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

    xliff_xml = build_xliff_document(
        units=units,
        provenance_records=prov_records,
        deployments=deps,
        versions=versions,
        project_name=project.name,
        doc_id=project_id,
    )
    await db.log_ingest_event(
        direction=IngestDirection.OUT, format="xliff", xliff_document_id=project_id, unit_count=len(units),
    )

    return Response(
        content=xliff_xml,
        media_type="application/xliff+xml",
        headers={"Content-Disposition": f'attachment; filename="project-{project.name}.xliff"'}
    )


@router.get("/{unit_id}/preview")
async def preview_xliff(unit_id: str):
    """Preview the XLIFF document as text (no download)."""
    db = get_db()
    cached = await db.get_xliff(unit_id)
    if cached:
        return {"xliff": cached}

    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    from app.xliff.xliff_service import build_single_unit_xliff
    xliff = build_single_unit_xliff(unit)
    return {"xliff": xliff}
