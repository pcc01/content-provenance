"""
JSON Provenance Document Service — the JSON peer of app/xliff/xliff_service.py.

Same job as the XLIFF service (produce/parse a self-contained document
carrying translation text + the complete embedded provenance chain), but
the encoding is far simpler: every piece of data involved
(TranslationUnit, ProvenanceRecord, DeploymentRecord,
TranslationUnitVersion) is already a Pydantic model, so
`model.model_dump(mode="json")` does the real serialization work — no
XLIFF-style note-based key=value packing needed.

Document shape (snake_case throughout, matching every other JSON response
in this API — e.g. GET /translations/{id} — rather than XLIFF's
PROV-notation-flavored camelCase note *keys*, which only existed because
those were embedded as note text, not real JSON keys):

    {
      "document_id": "...", "project_name": "...", "created_at": "...",
      "tool": "...", "tool_version": "...", "prov_conformance": "W3C PROV-DM 2013",
      "source_language": "en-US", "target_language": "fr-FR",
      "units": [
        {
          ...TranslationUnit fields (id, source_text, target_text, ...)...,
          "provenance": { ...ProvenanceRecord fields... } | null,
          "deployments": [ ...DeploymentRecord fields... ],
          "version_history": [ ...TranslationUnitVersion fields... ]
        }
      ]
    }

No caching table backs this the way xliff_documents caches rendered XML —
JSON serialization is cheap (no pretty-print pass), so callers just build
it fresh from current DB state every time (see app/api/json_export.py).

Import side (parse_json_document) is deliberately lenient: this system's
own exports use the canonical field names above, but an externally
supplied JSON file may be a bare list of units, a single bare unit object,
or use a handful of common alias field names (sourceText/source/text for
source_text, etc.) instead. Whatever "provenance"/"deployments"/
"version_history" a parsed unit carries is ignored by the importer (see
json_import.py) — provenance is always rebuilt fresh server-side, exactly
like app/xliff/xliff_import.py already does for XLIFF.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.schemas import (
    DeploymentRecord, ProvenanceRecord, TranslationUnit, TranslationUnitVersion,
)

PROV_CONFORMANCE = "W3C PROV-DM 2013"

# canonical field name -> accepted aliases (canonical name always included
# first so a match against our own exports is a same-key lookup).
_FIELD_ALIASES: Dict[str, tuple] = {
    "id":                 ("id",),
    "source_text":        ("source_text", "sourceText", "source", "text"),
    "source_language":    ("source_language", "sourceLanguage", "source_lang", "sourceLang"),
    "target_text":        ("target_text", "targetText", "target"),
    "target_language":    ("target_language", "targetLanguage", "target_lang", "targetLang"),
    "translation_method": ("translation_method", "translationMethod", "method"),
    "status":             ("status", "state"),
    "confidence_score":   ("confidence_score", "confidenceScore"),
    "quality_score":      ("quality_score", "qualityScore"),
    "metadata":           ("metadata",),
}
_ALL_ALIASES = {alias for aliases in _FIELD_ALIASES.values() for alias in aliases}


# ── Public API ────────────────────────────────────────────────────────────────

def build_json_document(
    units: List[TranslationUnit],
    provenance_records: Dict[str, ProvenanceRecord],
    deployments: Dict[str, List[DeploymentRecord]],
    project_name: str = "Translation Project",
    doc_id: Optional[str] = None,
    versions: Optional[Dict[str, List[TranslationUnitVersion]]] = None,
) -> Dict[str, Any]:
    """Build a full JSON provenance document for one or more units — the
    JSON peer of xliff_service.build_xliff_document."""
    doc_id = doc_id or str(uuid.uuid4())
    return {
        "document_id": doc_id,
        "project_name": project_name,
        "created_at": _now_iso(),
        "tool": settings.xliff_tool_name,
        "tool_version": settings.xliff_tool_version,
        "prov_conformance": PROV_CONFORMANCE,
        "source_language": units[0].source_language if units else "en",
        "target_language": units[0].target_language if units else "",
        "units": [
            _build_unit_json(
                unit,
                provenance_records.get(unit.id),
                deployments.get(unit.id, []),
                (versions or {}).get(unit.id, []),
            )
            for unit in units
        ],
    }


def build_single_unit_json(unit: TranslationUnit) -> Dict[str, Any]:
    """Convenience wrapper: JSON document for a single unit without
    pre-built provenance — the JSON peer of xliff_service.build_single_unit_xliff."""
    return build_json_document(
        units=[unit], provenance_records={}, deployments={},
        project_name=f"Unit {unit.id[:8]}", doc_id=unit.id,
    )


def parse_json_document(json_content: str) -> List[Dict[str, Any]]:
    """
    Parse a JSON provenance document — either this system's own extensive
    export, or a plain/minimal externally-supplied file — into a list of
    normalized unit dicts (canonical field names per _FIELD_ALIASES above).

    Accepts three top-level shapes:
      * {"units": [...]}                — this system's own document shape
      * [...]                           — a bare array of unit objects
      * {"source_text": ..., ...}       — a single bare unit, no wrapper
    """
    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if isinstance(data, list):
        raw_units = data
    elif isinstance(data, dict):
        raw_units = data.get("units")
        if raw_units is None:
            raw_units = [data] if _looks_like_unit(data) else []
    else:
        raise ValueError("Unsupported JSON shape: expected a JSON object or array of units")

    if not raw_units:
        raise ValueError("No translation units found in the supplied JSON document")

    normalized = [_normalize_unit(u) for u in raw_units]
    if not any(u.get("source_text") for u in normalized):
        raise ValueError("No translation units found in the supplied JSON document")
    return normalized


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_unit_json(
    unit: TranslationUnit,
    prov: Optional[ProvenanceRecord],
    deps: List[DeploymentRecord],
    unit_versions: List[TranslationUnitVersion],
) -> Dict[str, Any]:
    data = unit.model_dump(mode="json")
    data["provenance"] = prov.model_dump(mode="json") if prov else None
    data["deployments"] = [d.model_dump(mode="json") for d in deps]
    data["version_history"] = [v.model_dump(mode="json") for v in unit_versions]
    return data


def _looks_like_unit(obj: Dict[str, Any]) -> bool:
    """True if a bare (non-"units"-wrapped) JSON object has at least one
    field this system recognizes as unit data, rather than being e.g. an
    empty object or pure document metadata with nothing to import."""
    return any(k in obj for k in _ALL_ALIASES)


def _normalize_unit(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Each unit must be a JSON object, got {type(raw).__name__}")
    normalized: Dict[str, Any] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in raw and raw[alias] is not None:
                normalized[canonical] = raw[alias]
                break
    return normalized


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
