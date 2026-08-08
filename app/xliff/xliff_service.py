"""
XLIFF 2.0 Service
Generates and parses XLIFF 2.0 documents with embedded W3C PROV-DM metadata.

Standards:
  • XLIFF 2.0  — ISO 21720:2017  (translation exchange format)
  • W3C PROV-DM — https://www.w3.org/TR/prov-dm/  (provenance data model)
  • Dublin Core — http://purl.org/dc/elements/1.1/ (bibliographic metadata)
  • BCP-47      — language tags (en-US, fr-FR …)

Integration design
──────────────────
Every <unit> in the XLIFF document carries a <notes> block that embeds the
COMPLETE W3C PROV-DM chain for that segment:

  prov:Entity IDs  (source, translation, reviewed, deployed variants)
  prov:Activity    (Translation, Review, Publication — with timestamps)
  prov:Agent       (AI model or human translator — with model version/org)
  prov:Relations   (wasGeneratedBy, wasDerivedFrom, wasAttributedTo …)
  provx: extension (confidence, quality score, deployment context/location)

This makes each XLIFF file a self-contained provenance artifact: any TMS or
CAT tool that reads the XLIFF also receives the full chain of custody without
needing to call the /provenance API separately.

The prov:bundleId attribute on the root <xliff> element and on each <unit>
links back to the API's /api/v1/provenance/{id}/prov-json endpoint.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from xml.dom import minidom
import xml.etree.ElementTree as ET

from app.models.schemas import (
    TranslationUnit, ProvenanceRecord, DeploymentRecord, TranslationUnitVersion,
)


# ── XML Namespace declarations ────────────────────────────────────────────────
XLIFF_NS = "urn:oasis:names:tc:xliff:document:2.0"
PROV_NS  = "http://www.w3.org/ns/prov#"
DC_NS    = "http://purl.org/dc/elements/1.1/"
XSD_NS   = "http://www.w3.org/2001/XMLSchema#"
PROVX_NS = "urn:ai-provenance:xliff-ext:1.0"   # custom extension namespace


def _register_namespaces() -> None:
    ET.register_namespace("",      XLIFF_NS)
    ET.register_namespace("prov",  PROV_NS)
    ET.register_namespace("dc",    DC_NS)
    ET.register_namespace("xsd",   XSD_NS)
    ET.register_namespace("provx", PROVX_NS)


# ── Public API ────────────────────────────────────────────────────────────────

def build_xliff_document(
    units: List[TranslationUnit],
    provenance_records: Dict[str, ProvenanceRecord],
    deployments: Dict[str, List[DeploymentRecord]],
    project_name: str = "Translation Project",
    doc_id: Optional[str] = None,
    versions: Optional[Dict[str, List[TranslationUnitVersion]]] = None,
) -> str:
    """
    Generate a fully-annotated XLIFF 2.0 document.

    Each <unit> embeds the complete W3C PROV-DM chain:
      • All prov:Entity IDs (source, translation, reviewed, deployed variants)
      • prov:Activity details (type, start/end time, method)
      • prov:Agent details (name, type, model version, organisation)
      • All prov:Relations as structured <note> elements
      • provx: extension attributes (confidence, quality, deployment context)
    """
    _register_namespaces()
    doc_id = doc_id or str(uuid.uuid4())

    root = ET.Element(f"{{{XLIFF_NS}}}xliff")
    root.set("version",   "2.0")
    root.set("srcLang",   units[0].source_language if units else "en")
    root.set("trgLang",   units[0].target_language if units else "")
    root.set(f"{{{PROV_NS}}}bundleId", f"bundle:{doc_id}")
    # xmlns:prov and xmlns:dc are NOT set manually here — ElementTree already
    # auto-declares them (register_namespace + the Clark-notation bundleId/
    # language attributes used below are enough to trigger it), and adding
    # them again as plain string attributes produces a duplicate xmlns:prov
    # attribute that expat then refuses to parse. xsd/provx have no real
    # Clark-notation usage anywhere in this tree (they only ever appear as
    # informal prefixes inside note *values*), so those two still need to be
    # declared by hand for the namespace to show up on the document at all.
    root.set("xmlns:xsd",   XSD_NS)
    root.set("xmlns:provx", PROVX_NS)

    file_el = ET.SubElement(root, f"{{{XLIFF_NS}}}file")
    file_el.set("id", doc_id)

    # File-level metadata
    file_notes = ET.SubElement(file_el, f"{{{XLIFF_NS}}}notes")
    _note(file_notes, "doc:projectName",      project_name,                          "provx:projectName")
    _note(file_notes, "doc:createdAt",        _now_iso(),                            f"{DC_NS}created")
    _note(file_notes, "doc:tool",             "AI Translation Provenance System",    "provx:tool")
    _note(file_notes, "doc:toolVersion",      "1.0.0",                              "provx:toolVersion")
    _note(file_notes, "doc:provConformance",  "W3C PROV-DM 2013",                  f"{PROV_NS}conformsTo")
    _note(file_notes, "doc:xliffStandard",    "XLIFF 2.0 (ISO 21720:2017)",        "provx:standard")
    _note(file_notes, "doc:provApiEndpoint",  "/api/v1/provenance/{unit_id}/prov-json", "provx:apiEndpoint")

    for unit in units:
        prov = provenance_records.get(unit.id)
        deps = deployments.get(unit.id, [])
        unit_versions = (versions or {}).get(unit.id, [])
        _build_unit(file_el, unit, prov, deps, unit_versions)

    return _pretty_xml(root)


def build_single_unit_xliff(unit: TranslationUnit) -> str:
    """Convenience wrapper: XLIFF for a single unit without pre-built provenance."""
    return build_xliff_document(
        units=[unit],
        provenance_records={},
        deployments={},
        project_name=f"Unit {unit.id[:8]}",
        doc_id=unit.id,
    )


def parse_xliff_document(xml_content: str) -> List[Dict[str, Any]]:
    """
    Parse an XLIFF 2.0 document and reconstruct structured provenance data.

    Returns one dict per <unit> with keys:
      id, source, target, source_language, target_language, state,
      prov_bundle_id, prov_entities, prov_activities, prov_agents,
      prov_relations, deployments, raw_notes
    """
    _register_namespaces()
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XLIFF XML: {exc}") from exc

    ns = {"x": XLIFF_NS, "prov": PROV_NS, "dc": DC_NS, "provx": PROVX_NS}
    units: List[Dict[str, Any]] = []

    for file_el in root.findall("x:file", ns):
        for unit_el in file_el.findall("x:unit", ns):
            rec: Dict[str, Any] = {
                "id":              unit_el.get("id"),
                "source":          None,
                "target":          None,
                "source_language": None,
                "target_language": None,
                "state":           "initial",
                "prov_bundle_id":  unit_el.get(f"{{{PROV_NS}}}bundleId"),
                "prov_entities":   [],
                "prov_activities": [],
                "prov_agents":     [],
                "prov_relations":  [],
                "deployments":     [],
                "version_history": [],
                "raw_notes":       {},
            }

            for note in unit_el.findall(".//x:note", ns):
                cat   = note.get("category", "")
                nid   = note.get("id", "")
                value = note.text or ""
                rec["raw_notes"][nid] = {"category": cat, "value": value}

                if cat == f"{PROV_NS}Entity":
                    rec["prov_entities"].append({"id": nid, "detail": value})
                elif cat == f"{PROV_NS}Activity":
                    rec["prov_activities"].append({"id": nid, "detail": value})
                elif cat == f"{PROV_NS}Agent":
                    rec["prov_agents"].append({"id": nid, "detail": value})
                elif cat.startswith(f"{PROV_NS}Relation:"):
                    rel_type = cat.split(":")[-1]
                    rec["prov_relations"].append(
                        {"type": rel_type, **_parse_kv(value)}
                    )
                elif cat == f"{PROVX_NS}:deployment":
                    rec["deployments"].append(_parse_kv(value))
                elif cat == f"{PROVX_NS}:version":
                    rec["version_history"].append(_parse_kv(value))

            for seg in unit_el.findall("x:segment", ns):
                rec["state"] = seg.get("state", "initial")
                src = seg.find("x:source", ns)
                tgt = seg.find("x:target", ns)
                if src is not None:
                    rec["source"]          = src.text
                    rec["source_language"] = src.get(f"{{{DC_NS}}}language", "")
                if tgt is not None:
                    rec["target"]          = tgt.text
                    rec["target_language"] = tgt.get(f"{{{DC_NS}}}language", "")

            units.append(rec)

    return units


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_unit(
    parent: ET.Element,
    unit: TranslationUnit,
    prov: Optional[ProvenanceRecord],
    deps: List[DeploymentRecord],
    versions: Optional[List[TranslationUnitVersion]] = None,
) -> None:
    """Build a <unit> element with complete embedded PROV metadata."""

    unit_el = ET.SubElement(parent, f"{{{XLIFF_NS}}}unit")
    unit_el.set("id", unit.id)
    if prov:
        unit_el.set(f"{{{PROV_NS}}}bundleId", prov.bundle_id)

    notes = ET.SubElement(unit_el, f"{{{XLIFF_NS}}}notes")

    # ── Core translation metadata ─────────────────────────────────────────────
    _note(notes, "unit:translationMethod", unit.translation_method.value,  f"{PROVX_NS}:translationMethod")
    _note(notes, "unit:sourceLanguage",    unit.source_language,           f"{DC_NS}language")
    _note(notes, "unit:targetLanguage",    unit.target_language,           f"{DC_NS}language")
    _note(notes, "unit:status",            unit.status.value,              f"{PROVX_NS}:status")
    if unit.translated_at:
        _note(notes, "unit:translatedAt",  _iso(unit.translated_at),      f"{DC_NS}date")
    if unit.confidence_score is not None:
        _note(notes, "unit:confidenceScore", str(unit.confidence_score),  f"{PROVX_NS}:confidenceScore")
    if unit.quality_score is not None:
        _note(notes, "unit:qualityScore",    str(unit.quality_score),     f"{PROVX_NS}:qualityScore")
    if unit.reviewed_by_agent_id:
        _note(notes, "unit:reviewedBy",    unit.reviewed_by_agent_id,     f"{PROVX_NS}:reviewedBy")
    if unit.reviewed_at:
        _note(notes, "unit:reviewedAt",    _iso(unit.reviewed_at),        f"{PROVX_NS}:reviewedAt")

    # ── W3C PROV — Entities ───────────────────────────────────────────────────
    if prov:
        for entity in prov.entities:
            attrs = "; ".join(f"{k}={v}" for k, v in entity.attributes.items() if v)
            _note(
                notes, entity.id,
                f"entityType={entity.entity_type}; generatedAt={_iso(entity.generated_at)}; {attrs}",
                f"{PROV_NS}Entity",
            )

        # ── W3C PROV — Activities ─────────────────────────────────────────────
        for act in prov.activities:
            meta = "; ".join(f"{k}={v}" for k, v in act.metadata.items() if v)
            detail = (
                f"activityType={act.activity_type}; "
                f"startedAt={_iso(act.started_at)}; "
                f"endedAt={_iso(act.ended_at or act.started_at)}; "
                f"agentId={act.agent_id}"
                + (f"; {meta}" if meta else "")
            )
            _note(notes, act.id, detail, f"{PROV_NS}Activity")

        # ── W3C PROV — Agents ─────────────────────────────────────────────────
        for agent in prov.agents:
            detail = (
                f"name={agent.name}; agentType={agent.agent_type}"
                + (f"; modelVersion={agent.model_version}" if agent.model_version else "")
                + (f"; organization={agent.organization}"  if agent.organization  else "")
            )
            _note(notes, agent.id, detail, f"{PROV_NS}Agent")

        # ── W3C PROV — Relations ──────────────────────────────────────────────
        # All six W3C PROV-DM relation types are embedded here dynamically.
        # rel_type is one of:
        #   wasGeneratedBy · wasDerivedFrom · wasAttributedTo
        #   used · wasAssociatedWith · wasInformedBy
        # Each becomes: <note category="prov:Relation:{rel_type}">…</note>
        # making the XLIFF a self-contained provenance artifact — no API call needed.
        for idx, rel in enumerate(prov.relations):
            rel_type = rel["type"]
            parts    = "; ".join(f"{k}={v}" for k, v in rel.items() if k != "type" and v)
            _note(
                notes,
                f"prov:rel:{idx}:{rel_type}",
                parts,
                f"{PROV_NS}Relation:{rel_type}",
            )

        # ── PROV bundle cross-reference ───────────────────────────────────────
        _note(notes, "prov:bundleId",    prov.bundle_id,           f"{PROV_NS}Bundle")
        _note(notes, "prov:generatedAt", _iso(prov.generated_at),  f"{PROV_NS}generatedAtTime")
        if prov.summary:
            _note(notes, "prov:summary", prov.summary,             f"{PROVX_NS}:summary")

    # ── Style/glossary brief (Phase 13, §9b.3) ────────────────────────────────
    # The StyleGuideRule/GlossaryTerm entities above are already fully
    # embedded via the generic prov:Entity loop; this consolidates them
    # into one plain-English note a vendor's linguist can read directly
    # without decoding PROV note syntax — so vendor-routed (not just
    # AI-routed) translation work gets the same style/glossary grounding.
    if prov:
        brief_lines = _style_brief_lines(prov)
        if brief_lines:
            _note(notes, "style:brief", "; ".join(brief_lines), f"{PROVX_NS}:styleBrief")

    # ── Deployment records ────────────────────────────────────────────────────
    for dep in deps:
        dep_val = (
            f"context={dep.context.value}; "
            f"location={dep.location}; "
            f"deployedAt={_iso(dep.deployed_at)}; "
            f"active={dep.is_active}; "
            f"depId={dep.id}"
            + (f"; version={dep.version}" if dep.version else "")
        )
        _note(notes, f"dep:{dep.id}", dep_val, f"{PROVX_NS}:deployment")

    # ── Version history ───────────────────────────────────────────────────────
    # Human-readable companion to the formal wasRevisionOf chain embedded above
    # via the generic PROV-Relation notes (see prov_builder.py) — this section
    # answers "who translated this, who overwrote it, and when" without having
    # to reconstruct it from the entity/relation graph.
    for v in (versions or []):
        version_detail = (
            f"version={v.version_number}; sourceEvent={v.source_event}; "
            f"translatedBy={v.translated_by_agent_id}; method={v.method.value}; "
            f"createdAt={_iso(v.created_at)}"
            + (f"; qualityScore={v.quality_score}" if v.quality_score is not None else "")
            + (f"; note={v.note}" if v.note else "")
        )
        _note(notes, f"version:{v.id}", version_detail, f"{PROVX_NS}:version")

    # ── <segment> ─────────────────────────────────────────────────────────────
    seg = ET.SubElement(unit_el, f"{{{XLIFF_NS}}}segment")
    seg.set("id",    f"seg-{unit.id}")
    seg.set("state", _xliff_state(unit.status))

    src_el = ET.SubElement(seg, f"{{{XLIFF_NS}}}source")
    src_el.set(f"{{{DC_NS}}}language", unit.source_language)
    src_el.text = unit.source_text

    tgt_el = ET.SubElement(seg, f"{{{XLIFF_NS}}}target")
    tgt_el.set(f"{{{DC_NS}}}language", unit.target_language)
    tgt_el.text = unit.target_text or ""


def _style_brief_lines(prov: ProvenanceRecord) -> List[str]:
    """Phase 13 — renders the ContextRetrieval entities already present in
    `prov.entities` (see app/core/prov_builder.py's §4d) as plain-English
    lines instead of PROV note key=value syntax."""
    lines: List[str] = []
    for e in prov.entities:
        if e.entity_type == "StyleGuideRule":
            rule_type = e.attributes.get("provx:ruleType", "rule")
            rule_text = e.attributes.get("provx:ruleText", "")
            lines.append(f"[{rule_type}] {rule_text}")
        elif e.entity_type == "GlossaryTerm":
            source_term = e.attributes.get("provx:sourceTerm", "")
            target_term = e.attributes.get("provx:targetTerm", "")
            do_not_translate = e.attributes.get("provx:doNotTranslate") == "True"
            if do_not_translate:
                lines.append(f"[glossary] Do not translate '{source_term}' — keep as-is")
            else:
                lines.append(f"[glossary] '{source_term}' -> '{target_term}'")
    return lines


def _pretty_xml(root: ET.Element) -> str:
    rough = ET.tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def _note(parent: ET.Element, note_id: str, text: str, category: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{XLIFF_NS}}}note")
    el.set("id",       note_id)
    el.set("category", category)
    el.text = text
    return el


def _xliff_state(status) -> str:
    return {
        "pending":     "initial",
        "in_progress": "translated",
        "completed":   "translated",
        "reviewed":    "reviewed",
        "published":   "final",
        "deprecated":  "final",
    }.get(status.value if hasattr(status, "value") else status, "initial")


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.isoformat(timespec="seconds") + "Z"


def _parse_kv(value: str) -> Dict[str, str]:
    """Parse 'key=value; key=value' string into a dict."""
    result = {}
    for pair in value.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result
