"""CMS push/pull orchestration — the business logic behind
app/api/integrations.py.

push_translation_to_cms mirrors app/api/translations.py's
record_deployment: write the translated field (+ provenance) to the CMS,
record a DeploymentRecord, then rebuild+save the unit's provenance so the
push itself becomes part of the provenance chain — the same step every
other deploy-adjacent endpoint in this codebase takes.

pull_source_from_cms deliberately stops at "fetched the text" — it does
NOT create a TranslationUnit itself. Pulling content and deciding how to
translate it (method/provider/model/context) are separate concerns; the
caller hands the returned source_text/source_id to the existing
POST /api/v1/translations to actually create one.
"""

from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.integrations.factory import get_cms_integration
from app.core.prov_builder import build_provenance_record
from app.models.schemas import DeploymentContext, DeploymentRecord


async def push_translation_to_cms(
    unit_id: str,
    provider: str,
    content_type: str,
    entry_id: str,
    field_name: str,
    locale: Optional[str] = None,
    provenance_field: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    unit = await db.get_translation_unit(unit_id)
    if not unit:
        raise LookupError(f"Translation unit {unit_id} not found")
    if not unit.target_text:
        raise ValueError(f"Translation unit {unit_id} has no target_text to push yet")

    prov = await db.get_provenance_by_unit(unit_id)
    if not prov:
        deps = await db.get_deployments_for_unit(unit_id)
        prov = await build_provenance_record(unit, deps)
        await db.save_provenance_record(prov)

    provenance_field = provenance_field or settings.cms_provenance_field
    integration = get_cms_integration(provider)
    cms_response = await integration.push_field(
        content_type, entry_id, field_name, unit.target_text,
        locale=locale,
        extra_fields={provenance_field: prov.model_dump(mode="json")},
    )

    location = f"{provider}:{content_type}:{entry_id}"
    if locale:
        location += f":{locale}"

    dep = DeploymentRecord(
        translation_unit_id=unit_id,
        context=DeploymentContext.CMS,
        location=location,
        deployed_by=f"cms-integration:{provider}",
        metadata={
            "provider": provider,
            "content_type": content_type,
            "entry_id": entry_id,
            "field_name": field_name,
            "locale": locale,
            "provenance_field": provenance_field,
        },
    )
    await db.save_deployment_record(dep)

    # Rebuild provenance now that a new deployment exists — otherwise
    # GET /provenance/{id} (and GET /json/{id}) keep serving the bundle
    # from before this push, same gap every other deploy path guards against.
    all_deps = await db.get_deployments_for_unit(unit_id)
    prov_record = await build_provenance_record(unit, all_deps)
    await db.save_provenance_record(prov_record)

    return {
        "deployment_id": dep.id,
        "provider": provider,
        "content_type": content_type,
        "entry_id": entry_id,
        "field_name": field_name,
        "locale": locale,
        "provenance_field": provenance_field,
        "cms_response": cms_response,
    }


async def pull_source_from_cms(
    provider: str,
    content_type: str,
    entry_id: str,
    field_name: str,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    integration = get_cms_integration(provider)
    text = await integration.pull_field(content_type, entry_id, field_name, locale=locale)
    if text is None:
        raise LookupError(
            f"{provider}:{content_type}/{entry_id} has no value for field '{field_name}'"
            + (f" (locale={locale})" if locale else "")
        )

    source_id = f"{provider}:{content_type}:{entry_id}:{field_name}"
    if locale:
        source_id += f":{locale}"

    return {
        "provider": provider,
        "content_type": content_type,
        "entry_id": entry_id,
        "field_name": field_name,
        "locale": locale,
        "source_text": text,
        "source_id": source_id,
    }
