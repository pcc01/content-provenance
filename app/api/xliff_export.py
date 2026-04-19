"""XLIFF 2.0 Export API endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from typing import List, Optional

from app.core.database import get_db
from app.xliff.xliff_service import build_xliff_document

router = APIRouter()


@router.get("/{unit_id}", response_class=Response)
async def export_xliff_unit(unit_id: str):
    """Export a single translation unit as XLIFF 2.0 XML."""
    db = get_db()
    
    # Check cache first
    cached = db.get_xliff(unit_id)
    if cached:
        return Response(content=cached, media_type="application/xliff+xml",
                       headers={"Content-Disposition": f'attachment; filename="translation-{unit_id[:8]}.xliff"'})
    
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    prov_records = {}
    prov = db.get_provenance_by_unit(unit_id)
    if prov:
        prov_records[unit_id] = prov
    
    deps = {unit_id: db.get_deployments_for_unit(unit_id)}
    
    xliff_xml = build_xliff_document(
        units=[unit],
        provenance_records=prov_records,
        deployments=deps,
        project_name=f"Export {unit_id[:8]}",
        doc_id=unit_id,
    )
    db.save_xliff(unit_id, xliff_xml)
    
    return Response(
        content=xliff_xml,
        media_type="application/xliff+xml",
        headers={"Content-Disposition": f'attachment; filename="translation-{unit_id[:8]}.xliff"'}
    )


@router.get("/project/{project_id}", response_class=Response)
async def export_xliff_project(project_id: str):
    """Export all translations in a project as a single XLIFF 2.0 document."""
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    units = [db.get_translation_unit(uid) for uid in project.translation_units]
    units = [u for u in units if u]
    if not units:
        raise HTTPException(status_code=404, detail="No translation units found in project")
    
    prov_records = {u.id: db.get_provenance_by_unit(u.id) for u in units}
    prov_records = {k: v for k, v in prov_records.items() if v}
    deps = {u.id: db.get_deployments_for_unit(u.id) for u in units}
    
    xliff_xml = build_xliff_document(
        units=units,
        provenance_records=prov_records,
        deployments=deps,
        project_name=project.name,
        doc_id=project_id,
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
    cached = db.get_xliff(unit_id)
    if cached:
        return {"xliff": cached}
    
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    from app.xliff.xliff_service import build_single_unit_xliff
    xliff = build_single_unit_xliff(unit)
    return {"xliff": xliff}
