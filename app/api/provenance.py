"""
Provenance API endpoints
GET  /api/v1/provenance/{unit_id}           - Full provenance for a translation
GET  /api/v1/provenance/{unit_id}/prov-json - W3C PROV-JSON serialization
GET  /api/v1/provenance/{unit_id}/prov-n    - Human-readable PROV-N notation
GET  /api/v1/provenance/{unit_id}/lineage   - Lineage graph (simplified)
GET  /api/v1/provenance/{unit_id}/deployments - All deployment records
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from typing import Dict, Any

from app.core.database import get_db
from app.core.prov_builder import build_provenance_record, to_prov_json

router = APIRouter()


@router.get("/{unit_id}")
async def get_provenance(unit_id: str) -> Dict[str, Any]:
    """
    Get the complete provenance record for a translation unit.
    Includes W3C PROV entities, activities, agents, and their relations.
    """
    db = get_db()
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    prov_record = db.get_provenance_by_unit(unit_id)
    if not prov_record:
        # Rebuild on the fly
        deps = db.get_deployments_for_unit(unit_id)
        prov_record = build_provenance_record(unit, deps)
    
    deployments = db.get_deployments_for_unit(unit_id)
    
    return {
        "translation_unit_id": unit_id,
        "source_text": unit.source_text,
        "target_text": unit.target_text,
        "source_language": unit.source_language,
        "target_language": unit.target_language,
        "translation_method": unit.translation_method.value,
        "status": unit.status.value,
        "provenance": {
            "bundle_id": prov_record.bundle_id,
            "generated_at": prov_record.generated_at.isoformat(),
            "summary": prov_record.summary,
            "entities": [e.model_dump() for e in prov_record.entities],
            "activities": [a.model_dump() for a in prov_record.activities],
            "agents": [ag.model_dump() for ag in prov_record.agents],
            "relations": prov_record.relations,
        },
        "deployments": [d.model_dump() for d in deployments],
        "xliff_document_id": unit_id,
    }


@router.get("/{unit_id}/prov-json")
async def get_prov_json(unit_id: str) -> Dict[str, Any]:
    """
    Return the W3C PROV-JSON serialization of the provenance record.
    Compliant with https://www.w3.org/Submission/prov-json/
    """
    db = get_db()
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    prov_record = db.get_provenance_by_unit(unit_id)
    if not prov_record:
        deps = db.get_deployments_for_unit(unit_id)
        prov_record = build_provenance_record(unit, deps)
    
    # Check cache
    cached = db.get_prov_json(prov_record.bundle_id)
    if cached:
        return cached
    
    prov_json = to_prov_json(prov_record)
    db.save_prov_json(prov_record.bundle_id, prov_json)
    return prov_json


@router.get("/{unit_id}/prov-n", response_class=PlainTextResponse)
async def get_prov_n(unit_id: str) -> str:
    """
    Return W3C PROV-N (human-readable) notation.
    Spec: https://www.w3.org/TR/prov-n/
    """
    db = get_db()
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    prov_record = db.get_provenance_by_unit(unit_id)
    if not prov_record:
        deps = db.get_deployments_for_unit(unit_id)
        prov_record = build_provenance_record(unit, deps)
    
    lines = [
        "// W3C PROV-N Notation",
        "// https://www.w3.org/TR/prov-n/",
        "//",
        f"// Generated: {prov_record.generated_at.isoformat()}Z",
        f"// Translation Unit: {unit_id}",
        "",
        f'document "{prov_record.bundle_id}"',
        "",
        "  // === PREFIX DECLARATIONS ===",
        "  prefix prov <http://www.w3.org/ns/prov#>",
        "  prefix provx <urn:ai-provenance-system:>",
        "  prefix dc <http://purl.org/dc/elements/1.1/>",
        "  prefix xsd <http://www.w3.org/2001/XMLSchema#>",
        "",
    ]
    
    # Entities
    lines.append("  // === ENTITIES ===")
    for e in prov_record.entities:
        attrs = ", ".join(f'{k}="{v}"' for k, v in e.attributes.items() if v)
        lines.append(f'  entity("{e.id}", [ prov:type="{e.entity_type}", {attrs} ])')
    lines.append("")
    
    # Agents
    lines.append("  // === AGENTS ===")
    for ag in prov_record.agents:
        lines.append(
            f'  agent("{ag.id}", [ prov:type="{ag.agent_type}", prov:label="{ag.name}"'
            + (f', provx:modelVersion="{ag.model_version}"' if ag.model_version else "")
            + " ])"
        )
    lines.append("")
    
    # Activities
    lines.append("  // === ACTIVITIES ===")
    for act in prov_record.activities:
        start = act.started_at.isoformat() + "Z"
        end = (act.ended_at or act.started_at).isoformat() + "Z"
        lines.append(
            f'  activity("{act.id}", "{start}", "{end}", '
            f'[ prov:type="{act.activity_type}" ])'
        )
    lines.append("")
    
    # Relations
    lines.append("  // === RELATIONS ===")
    for rel in prov_record.relations:
        rtype = rel["type"]
        if rtype == "wasGeneratedBy":
            lines.append(f'  wasGeneratedBy("{rel["entity"]}", "{rel["activity"]}", -)')
        elif rtype == "wasDerivedFrom":
            lines.append(f'  wasDerivedFrom("{rel["generatedEntity"]}", "{rel["usedEntity"]}", -, -, -)')
        elif rtype == "wasAttributedTo":
            lines.append(f'  wasAttributedTo("{rel["entity"]}", "{rel["agent"]}")')
        elif rtype == "used":
            lines.append(f'  used("{rel["activity"]}", "{rel["entity"]}", -)')
        elif rtype == "wasAssociatedWith":
            role = rel.get("role", "-")
            lines.append(f'  wasAssociatedWith("{rel["activity"]}", "{rel["agent"]}", "{role}")')
        elif rtype == "wasInformedBy":
            lines.append(f'  wasInformedBy("{rel["informed"]}", "{rel["informant"]}")')
    
    lines.extend(["", "endDocument"])
    return "\n".join(lines)


@router.get("/{unit_id}/lineage")
async def get_lineage(unit_id: str) -> Dict[str, Any]:
    """
    Return a simplified lineage graph for visualization.
    Nodes = entities + agents, Edges = relations.
    """
    db = get_db()
    unit = db.get_translation_unit(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    
    prov_record = db.get_provenance_by_unit(unit_id)
    if not prov_record:
        deps = db.get_deployments_for_unit(unit_id)
        prov_record = build_provenance_record(unit, deps)
    
    nodes = []
    edges = []
    
    for e in prov_record.entities:
        nodes.append({
            "id": e.id,
            "label": e.entity_type,
            "type": "entity",
            "generated_at": e.generated_at.isoformat(),
            "attributes": e.attributes,
        })
    
    for act in prov_record.activities:
        nodes.append({
            "id": act.id,
            "label": act.activity_type,
            "type": "activity",
            "started_at": act.started_at.isoformat(),
        })
    
    for ag in prov_record.agents:
        nodes.append({
            "id": ag.id,
            "label": ag.name,
            "type": "agent",
            "agent_type": ag.agent_type,
        })
    
    for rel in prov_record.relations:
        rtype = rel["type"]
        if rtype == "wasGeneratedBy":
            edges.append({"from": rel["entity"], "to": rel["activity"], "label": "wasGeneratedBy"})
        elif rtype == "wasDerivedFrom":
            edges.append({"from": rel["generatedEntity"], "to": rel["usedEntity"], "label": "wasDerivedFrom"})
        elif rtype == "wasAttributedTo":
            edges.append({"from": rel["entity"], "to": rel["agent"], "label": "wasAttributedTo"})
        elif rtype == "used":
            edges.append({"from": rel["activity"], "to": rel["entity"], "label": "used"})
        elif rtype == "wasAssociatedWith":
            edges.append({"from": rel["activity"], "to": rel["agent"], "label": "wasAssociatedWith"})
        elif rtype == "wasInformedBy":
            edges.append({"from": rel["informed"], "to": rel["informant"], "label": "wasInformedBy"})
    
    return {
        "translation_unit_id": unit_id,
        "nodes": nodes,
        "edges": edges,
        "summary": prov_record.summary,
    }


@router.get("/{unit_id}/deployments")
async def get_deployments(unit_id: str):
    """List all deployment records for a translation unit."""
    db = get_db()
    if not db.get_translation_unit(unit_id):
        raise HTTPException(status_code=404, detail=f"Translation unit {unit_id} not found")
    deployments = db.get_deployments_for_unit(unit_id)
    return [d.model_dump() for d in deployments]
