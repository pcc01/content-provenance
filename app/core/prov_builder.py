"""
W3C PROV-DM Provenance Builder
Constructs compliant provenance records following the W3C PROV Data Model.

Spec: https://www.w3.org/TR/prov-dm/
Serialization: PROV-JSON (https://www.w3.org/Submission/prov-json/)

Core PROV-DM concepts used:
  Entity     - a thing with identity (source text, translation, deployment)
  Activity   - something that occurs (translation act, review, publication)
  Agent      - responsible party (AI model, human translator, organization)
  
Relations:
  wasGeneratedBy(entity, activity)
  wasDerivedFrom(entity, entity)
  wasAttributedTo(entity, agent)
  used(activity, entity)
  wasAssociatedWith(activity, agent)
  wasInformedBy(activity, activity)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from app.models.schemas import (
    TranslationUnit, ProvenanceRecord, ProvenanceAgent,
    ProvenanceActivity, ProvenanceEntity, DeploymentRecord,
    TranslationMethod, ImageAsset, ImageTranslationUnit,
)
from app.core.database import get_db


PROV_PREFIX = "http://www.w3.org/ns/prov#"
PROVX_PREFIX = "urn:ai-provenance-system:"
XSD_PREFIX = "http://www.w3.org/2001/XMLSchema#"


async def build_provenance_record(
    unit: TranslationUnit,
    deployments: Optional[List[DeploymentRecord]] = None,
) -> ProvenanceRecord:
    """
    Construct a complete W3C PROV-DM provenance record for a translation unit.
    
    Provenance graph:
    
    source_entity --[wasDerivedFrom]-- (original source doc)
    source_entity --[used]-- translation_activity
    translation_entity --[wasGeneratedBy]-- translation_activity
    translation_entity --[wasDerivedFrom]-- source_entity
    translation_entity --[wasAttributedTo]-- translator_agent
    translation_activity --[wasAssociatedWith]-- translator_agent
    [if reviewed]:
      reviewed_entity --[wasGeneratedBy]-- review_activity
      review_activity --[wasInformedBy]-- translation_activity
      review_activity --[wasAssociatedWith]-- reviewer_agent
    [if deployed]:
      deployed_entity --[wasGeneratedBy]-- deployment_activity
      deployed_entity --[wasDerivedFrom]-- translation_entity
    """
    db = get_db()
    
    entities: List[ProvenanceEntity] = []
    activities: List[ProvenanceActivity] = []
    agents: List[ProvenanceAgent] = []
    relations: List[Dict[str, str]] = []
    
    # ── 1. Source Entity ──────────────────────────────────────────────────────
    source_entity = ProvenanceEntity(
        id=f"entity:source:{unit.source_id}",
        entity_type="SourceText",
        generated_at=datetime.utcnow(),
        attributes={
            "prov:type": "prov:Entity",
            "provx:contentType": "text/plain",
            "provx:language": unit.source_language,
            "provx:textSnippet": unit.source_text[:100],
            "dc:format": "text/plain",
        }
    )
    entities.append(source_entity)
    
    # ── 2. Translator Agent ───────────────────────────────────────────────────
    translator_agent = await db.get_agent(unit.translated_by_agent_id)
    if not translator_agent:
        translator_agent = ProvenanceAgent(
            id=unit.translated_by_agent_id,
            name="Unknown Agent",
            agent_type="SoftwareAgent",
        )
    agents.append(translator_agent)
    
    # ── 3. Translation Activity ───────────────────────────────────────────────
    translation_activity = ProvenanceActivity(
        id=f"activity:translate:{unit.id}",
        activity_type="Translation",
        started_at=unit.translated_at or datetime.utcnow(),
        ended_at=unit.translated_at,
        agent_id=translator_agent.id,
        used_entity_ids=[source_entity.id],
        metadata={
            "prov:type": "provx:TranslationActivity",
            "provx:method": unit.translation_method.value,
            "provx:sourceLanguage": unit.source_language,
            "provx:targetLanguage": unit.target_language,
            "provx:confidenceScore": str(unit.confidence_score) if unit.confidence_score else None,
            "provx:domain": unit.metadata.get("domain"),
        }
    )
    activities.append(translation_activity)
    
    # Relation: translation_activity used source_entity
    relations.append({
        "type": "used",
        "activity": translation_activity.id,
        "entity": source_entity.id,
        "time": (unit.translated_at or datetime.utcnow()).isoformat(),
    })
    
    # Relation: translation_activity wasAssociatedWith translator_agent
    relations.append({
        "type": "wasAssociatedWith",
        "activity": translation_activity.id,
        "agent": translator_agent.id,
        "role": _agent_role(unit.translation_method),
    })
    
    # ── 4. Translation Entity ─────────────────────────────────────────────────
    translation_entity = ProvenanceEntity(
        id=f"entity:translation:{unit.id}",
        entity_type="Translation",
        was_generated_by=translation_activity.id,
        was_derived_from=source_entity.id,
        was_attributed_to=translator_agent.id,
        generated_at=unit.translated_at or datetime.utcnow(),
        attributes={
            "prov:type": "provx:TranslationEntity",
            "provx:translationMethod": unit.translation_method.value,
            "provx:targetLanguage": unit.target_language,
            "provx:status": unit.status.value,
            "provx:qualityScore": str(unit.quality_score) if unit.quality_score else None,
            "provx:confidenceScore": str(unit.confidence_score) if unit.confidence_score else None,
            "provx:textSnippet": (unit.target_text or "")[:100],
        }
    )
    entities.append(translation_entity)
    
    # Relations for translation entity
    relations.append({
        "type": "wasGeneratedBy",
        "entity": translation_entity.id,
        "activity": translation_activity.id,
        "time": (unit.translated_at or datetime.utcnow()).isoformat(),
    })
    relations.append({
        "type": "wasDerivedFrom",
        "generatedEntity": translation_entity.id,
        "usedEntity": source_entity.id,
        "activity": translation_activity.id,
    })
    relations.append({
        "type": "wasAttributedTo",
        "entity": translation_entity.id,
        "agent": translator_agent.id,
    })

    # ── 4b. Version history (wasRevisionOf chain) ─────────────────────────────
    # translation_entity above always represents the CURRENT/latest version —
    # its id is deterministic per unit, not per version, so it doesn't need
    # its own place in the chain. Prior versions each get their own entity id
    # and a wasRevisionOf edge to the version before them, ending with an edge
    # from the current entity back to the last prior version. Units with only
    # one version (the common case until Phase 3's redrive engine or a human
    # edit produces a second one) add nothing here.
    versions = await db.list_translation_unit_versions(unit.id)
    if len(versions) > 1:
        prior_versions = versions[:-1]  # excludes the current/latest version
        prev_entity_id: Optional[str] = None
        for v in prior_versions:
            hist_entity = ProvenanceEntity(
                id=f"entity:translation:{unit.id}:v{v.version_number}",
                entity_type="Translation",
                was_derived_from=prev_entity_id or source_entity.id,
                was_attributed_to=v.translated_by_agent_id,
                generated_at=v.created_at,
                attributes={
                    "prov:type": "provx:TranslationEntity",
                    "provx:version": str(v.version_number),
                    "provx:sourceEvent": v.source_event,
                    "provx:qualityScore": str(v.quality_score) if v.quality_score is not None else None,
                    "provx:textSnippet": (v.target_text or "")[:100],
                },
            )
            entities.append(hist_entity)
            if prev_entity_id:
                relations.append({
                    "type": "wasRevisionOf",
                    "newerEntity": hist_entity.id,
                    "olderEntity": prev_entity_id,
                })
            prev_entity_id = hist_entity.id
        relations.append({
            "type": "wasRevisionOf",
            "newerEntity": translation_entity.id,
            "olderEntity": prev_entity_id,
        })

    # ── 4c. Quality Assessment (Phase 3 — threshold-quality redrive) ─────────
    # The most recent QualityScore, if any, gets its own Activity — separate
    # from the Translation activity so it's clear WHO/WHAT judged the
    # quality (a scorer agent) vs WHO/WHAT produced the translation. When the
    # current version was itself produced by a redrive (source_event ==
    # "redrive"), the Translation activity is additionally marked
    # wasInformedBy that assessment — the formal PROV link for "this
    # translation exists BECAUSE that assessment flagged the prior one."
    latest_score = await db.get_latest_quality_score(unit.id)
    if latest_score is not None:
        scorer_agent = await db.get_or_create_agent(
            name=f"scorer:{latest_score.scorer}", agent_type="SoftwareAgent",
            metadata={"role": "quality_scorer"},
        )
        if scorer_agent not in agents:
            agents.append(scorer_agent)

        qa_activity = ProvenanceActivity(
            id=f"activity:qa:{latest_score.id}",
            activity_type="QualityAssessment",
            started_at=latest_score.scored_at,
            ended_at=latest_score.scored_at,
            agent_id=scorer_agent.id,
            used_entity_ids=[translation_entity.id],
            metadata={
                "prov:type": "provx:QualityAssessmentActivity",
                "provx:score": str(latest_score.score) if latest_score.score is not None else None,
                "provx:reasons": ",".join(latest_score.reasons) if latest_score.reasons else None,
            },
        )
        activities.append(qa_activity)
        relations.append({"type": "used", "activity": qa_activity.id, "entity": translation_entity.id})
        relations.append({"type": "wasAssociatedWith", "activity": qa_activity.id, "agent": scorer_agent.id})

        if versions and versions[-1].source_event == "redrive":
            relations.append({
                "type": "wasInformedBy",
                "informed": translation_activity.id,
                "informant": qa_activity.id,
            })

    # ── 4d. Context Retrieval (Phase 13 — GraphRAG style/voice context) ──────
    # Read back from graph_edges rather than taking retrieval results as a
    # parameter: like everything else in this rebuild-from-scratch function,
    # provenance has to reconstruct correctly on ANY rebuild (review, deploy,
    # revert, ...), not just the one call site that originally ran
    # retrieval — see app/core/graph/builder.record_unit_style_context,
    # called once retrieval context is actually used for a translation.
    unit_node = await db.get_graph_node("Unit", unit.id)
    if unit_node is not None:
        rule_neighbors = await db.list_neighbors(unit_node.id, edge_type="appliedRule", direction="out")
        term_neighbors = await db.list_neighbors(unit_node.id, edge_type="usedTerm", direction="out")
        style_entities: List[ProvenanceEntity] = []
        for node in rule_neighbors:
            rule = await db.get_style_guide_rule(node.ref_id)
            if rule:
                style_entities.append(ProvenanceEntity(
                    id=f"entity:style-rule:{rule.id}",
                    entity_type="StyleGuideRule",
                    generated_at=rule.created_at,
                    attributes={
                        "prov:type": "provx:StyleGuideRule",
                        "provx:ruleType": rule.rule_type.value,
                        "provx:ruleText": rule.rule_text[:200],
                        "provx:severity": rule.severity.value,
                    },
                ))
        for node in term_neighbors:
            term = await db.get_glossary_term(node.ref_id)
            if term:
                style_entities.append(ProvenanceEntity(
                    id=f"entity:glossary-term:{term.id}",
                    entity_type="GlossaryTerm",
                    generated_at=term.created_at,
                    attributes={
                        "prov:type": "provx:GlossaryTerm",
                        "provx:sourceTerm": term.source_term,
                        "provx:targetTerm": term.target_term or "",
                        "provx:doNotTranslate": str(term.do_not_translate),
                    },
                ))

        if style_entities:
            entities.extend(style_entities)
            retrieval_agent = await db.get_or_create_agent(
                name="graph-retrieval", agent_type="SoftwareAgent",
                metadata={"role": "style_context_retrieval"},
            )
            if retrieval_agent not in agents:
                agents.append(retrieval_agent)

            retrieval_activity = ProvenanceActivity(
                id=f"activity:context-retrieval:{unit.id}",
                activity_type="ContextRetrieval",
                started_at=unit.translated_at or datetime.utcnow(),
                ended_at=unit.translated_at,
                agent_id=retrieval_agent.id,
                used_entity_ids=[e.id for e in style_entities],
                metadata={
                    "prov:type": "provx:ContextRetrievalActivity",
                    "provx:factCount": str(len(style_entities)),
                },
            )
            activities.append(retrieval_activity)
            relations.append({
                "type": "wasAssociatedWith", "activity": retrieval_activity.id, "agent": retrieval_agent.id,
            })
            for e in style_entities:
                relations.append({"type": "used", "activity": retrieval_activity.id, "entity": e.id})
            # The formal PROV link answering "why did the model choose this
            # tone" — the translation activity was INFORMED BY whatever
            # style/glossary context it was given.
            relations.append({
                "type": "wasInformedBy",
                "informed": translation_activity.id,
                "informant": retrieval_activity.id,
            })

    # ── 4e. Style Adherence Assessment (Phase 13) ─────────────────────────────
    # Same shape as 4c's QualityAssessment — a separate Activity so it's
    # clear WHO/WHAT judged tone/voice/terminology adherence, distinct from
    # both the Translation activity and the accuracy-focused QA one.
    latest_style_score = await db.get_latest_style_adherence_score(unit.id)
    if latest_style_score is not None:
        style_scorer_agent = await db.get_or_create_agent(
            name=f"style-scorer:{latest_style_score.scorer}", agent_type="SoftwareAgent",
            metadata={"role": "style_adherence_scorer"},
        )
        if style_scorer_agent not in agents:
            agents.append(style_scorer_agent)

        style_qa_activity = ProvenanceActivity(
            id=f"activity:style-qa:{latest_style_score.id}",
            activity_type="StyleAdherenceAssessment",
            started_at=latest_style_score.scored_at,
            ended_at=latest_style_score.scored_at,
            agent_id=style_scorer_agent.id,
            used_entity_ids=[translation_entity.id],
            metadata={
                "prov:type": "provx:StyleAdherenceAssessmentActivity",
                "provx:overallScore": (
                    str(latest_style_score.overall_score) if latest_style_score.overall_score is not None else None
                ),
                "provx:toneScore": (
                    str(latest_style_score.tone_score) if latest_style_score.tone_score is not None else None
                ),
                "provx:voiceScore": (
                    str(latest_style_score.voice_score) if latest_style_score.voice_score is not None else None
                ),
                "provx:terminologyScore": (
                    str(latest_style_score.terminology_score)
                    if latest_style_score.terminology_score is not None else None
                ),
            },
        )
        activities.append(style_qa_activity)
        relations.append({"type": "used", "activity": style_qa_activity.id, "entity": translation_entity.id})
        relations.append({
            "type": "wasAssociatedWith", "activity": style_qa_activity.id, "agent": style_scorer_agent.id,
        })

    # ── 5. Review (if applicable) ─────────────────────────────────────────────
    if unit.reviewed_by_agent_id:
        reviewer_agent = await db.get_agent(unit.reviewed_by_agent_id)
        if not reviewer_agent:
            reviewer_agent = ProvenanceAgent(
                id=unit.reviewed_by_agent_id,
                name="Reviewer",
                agent_type="Person",
            )
        if reviewer_agent not in agents:
            agents.append(reviewer_agent)
        
        review_activity = ProvenanceActivity(
            id=f"activity:review:{unit.id}",
            activity_type="Review",
            started_at=unit.reviewed_at or datetime.utcnow(),
            ended_at=unit.reviewed_at,
            agent_id=reviewer_agent.id,
            used_entity_ids=[translation_entity.id],
            metadata={"prov:type": "provx:ReviewActivity"}
        )
        activities.append(review_activity)
        
        reviewed_entity = ProvenanceEntity(
            id=f"entity:reviewed:{unit.id}",
            entity_type="ReviewedTranslation",
            was_generated_by=review_activity.id,
            was_derived_from=translation_entity.id,
            was_attributed_to=reviewer_agent.id,
            generated_at=unit.reviewed_at or datetime.utcnow(),
            attributes={"prov:type": "provx:ReviewedTranslation", "provx:reviewStatus": "approved"}
        )
        entities.append(reviewed_entity)
        
        relations.extend([
            {"type": "wasInformedBy", "informed": review_activity.id, "informant": translation_activity.id},
            {"type": "wasAssociatedWith", "activity": review_activity.id, "agent": reviewer_agent.id, "role": "prov:Reviewer"},
            {"type": "wasGeneratedBy", "entity": reviewed_entity.id, "activity": review_activity.id},
        ])
    
    # ── 6. Deployments ────────────────────────────────────────────────────────
    for dep in (deployments or []):
        system_agent = await db.get_or_create_agent("System", "SoftwareAgent")
        if system_agent not in agents:
            agents.append(system_agent)
        
        dep_activity = ProvenanceActivity(
            id=f"activity:deploy:{dep.id}",
            activity_type="Publication",
            started_at=dep.deployed_at,
            ended_at=dep.deployed_at,
            agent_id=system_agent.id,
            metadata={
                "prov:type": "provx:PublicationActivity",
                "provx:deploymentContext": dep.context.value,
                "provx:deploymentLocation": dep.location,
            }
        )
        activities.append(dep_activity)
        
        dep_entity = ProvenanceEntity(
            id=f"entity:deployment:{dep.id}",
            entity_type="DeployedContent",
            was_generated_by=dep_activity.id,
            was_derived_from=translation_entity.id,
            was_attributed_to=system_agent.id,
            generated_at=dep.deployed_at,
            attributes={
                "prov:type": "provx:DeployedContent",
                "provx:context": dep.context.value,
                "provx:location": dep.location,
                "provx:isActive": str(dep.is_active),
                "provx:version": dep.version or "1.0",
            }
        )
        entities.append(dep_entity)
        
        relations.extend([
            {"type": "wasGeneratedBy", "entity": dep_entity.id, "activity": dep_activity.id},
            {"type": "wasDerivedFrom", "generatedEntity": dep_entity.id, "usedEntity": translation_entity.id},
            {"type": "wasAssociatedWith", "activity": dep_activity.id, "agent": system_agent.id},
        ])
    
    # ── 7. Build Summary ──────────────────────────────────────────────────────
    summary = _build_summary(unit, translator_agent, deployments or [])
    
    record = ProvenanceRecord(
        translation_unit_id=unit.id,
        entities=entities,
        activities=activities,
        agents=agents,
        relations=relations,
        summary=summary,
        # Cross-reference: the XLIFF document that carries this provenance
        xliff_document_id=unit.id,
    )

    return record


async def build_image_provenance_record(
    itu: ImageTranslationUnit,
    source_asset: ImageAsset,
    target_asset: Optional[ImageAsset] = None,
) -> ProvenanceRecord:
    """
    Same PROV-DM pattern as build_provenance_record, for image assets:

    source_entity(SourceImage) --[used]-- translation_activity
    translation_activity --[wasAssociatedWith]-- translator_agent
    [if localized]:
      translated_entity(TranslatedImage) --[wasGeneratedBy]-- translation_activity
      translated_entity --[wasDerivedFrom]-- source_entity
      translated_entity --[wasAttributedTo]-- translator_agent

    Deliberately minimal compared to the text version — no review/deployment/
    version-history sections yet; images get those treatments if/when this
    phase's usage shows they're needed.
    """
    db = get_db()

    entities: List[ProvenanceEntity] = []
    activities: List[ProvenanceActivity] = []
    agents: List[ProvenanceAgent] = []
    relations: List[Dict[str, str]] = []

    source_entity = ProvenanceEntity(
        id=f"entity:source-image:{source_asset.id}",
        entity_type="SourceImage",
        generated_at=source_asset.uploaded_at,
        attributes={
            "prov:type": "prov:Entity",
            "provx:contentType": source_asset.content_type,
            "provx:checksum": source_asset.checksum,
            "provx:language": itu.source_language,
        },
    )
    entities.append(source_entity)

    translator_agent = await db.get_agent(itu.translated_by_agent_id)
    if not translator_agent:
        translator_agent = ProvenanceAgent(
            id=itu.translated_by_agent_id, name="Unknown Agent", agent_type="SoftwareAgent",
        )
    agents.append(translator_agent)

    translation_activity = ProvenanceActivity(
        id=f"activity:translate-image:{itu.id}",
        activity_type="ImageTranslation",
        started_at=itu.translated_at or datetime.utcnow(),
        ended_at=itu.translated_at,
        agent_id=translator_agent.id,
        used_entity_ids=[source_entity.id],
        metadata={
            "prov:type": "provx:ImageTranslationActivity",
            "provx:method": itu.translation_method.value,
            "provx:sourceLanguage": itu.source_language,
            "provx:targetLanguage": itu.target_language,
        },
    )
    activities.append(translation_activity)

    relations.append({
        "type": "used", "activity": translation_activity.id, "entity": source_entity.id,
        "time": (itu.translated_at or datetime.utcnow()).isoformat(),
    })
    relations.append({
        "type": "wasAssociatedWith", "activity": translation_activity.id,
        "agent": translator_agent.id, "role": _agent_role(itu.translation_method),
    })

    translated_entity: Optional[ProvenanceEntity] = None
    if target_asset is not None:
        translated_entity = ProvenanceEntity(
            id=f"entity:translated-image:{itu.id}",
            entity_type="TranslatedImage",
            was_generated_by=translation_activity.id,
            was_derived_from=source_entity.id,
            was_attributed_to=translator_agent.id,
            generated_at=target_asset.uploaded_at,
            attributes={
                "prov:type": "provx:TranslatedImageEntity",
                "provx:contentType": target_asset.content_type,
                "provx:checksum": target_asset.checksum,
                "provx:targetLanguage": itu.target_language,
                "provx:status": itu.status.value,
                "provx:qualityScore": str(itu.quality_score) if itu.quality_score is not None else None,
            },
        )
        entities.append(translated_entity)
        relations.append({
            "type": "wasGeneratedBy", "entity": translated_entity.id,
            "activity": translation_activity.id, "time": target_asset.uploaded_at.isoformat(),
        })
        relations.append({
            "type": "wasDerivedFrom", "generatedEntity": translated_entity.id,
            "usedEntity": source_entity.id, "activity": translation_activity.id,
        })
        relations.append({
            "type": "wasAttributedTo", "entity": translated_entity.id, "agent": translator_agent.id,
        })

    summary = (
        f"Image {source_asset.id[:8]} translated from {itu.source_language} to "
        f"{itu.target_language} by {translator_agent.name} "
        f"({'localized' if translated_entity else 'pending localization'})."
    )

    return ProvenanceRecord(
        translation_unit_id=itu.id,
        entities=entities, activities=activities, agents=agents, relations=relations,
        summary=summary,
    )


def to_prov_json(record: ProvenanceRecord) -> Dict[str, Any]:
    """
    Serialize a ProvenanceRecord to W3C PROV-JSON format.
    Spec: https://www.w3.org/Submission/prov-json/
    """
    prefix = {
        "prov": "http://www.w3.org/ns/prov#",
        "provx": "urn:ai-provenance-system:",
        "dc": "http://purl.org/dc/elements/1.1/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "xliff": "urn:oasis:names:tc:xliff:document:2.0",
    }
    
    doc = {
        "prefix": prefix,
        "bundle": {
            record.bundle_id: {
                "entity": {},
                "activity": {},
                "agent": {},
                "wasGeneratedBy": {},
                "wasDerivedFrom": {},
                "wasAttributedTo": {},
                "used": {},
                "wasAssociatedWith": {},
                "wasInformedBy": {},
                "wasRevisionOf": {},
            }
        }
    }
    
    bundle = doc["bundle"][record.bundle_id]
    
    for entity in record.entities:
        bundle["entity"][entity.id] = {
            "prov:type": {"$": entity.entity_type, "type": "xsd:string"},
            **{k: {"$": v, "type": "xsd:string"} for k, v in entity.attributes.items() if v},
        }
    
    for activity in record.activities:
        bundle["activity"][activity.id] = {
            "prov:type": {"$": activity.activity_type, "type": "xsd:string"},
            "prov:startTime": {"$": activity.started_at.isoformat() + "Z", "type": "xsd:dateTime"},
            "prov:endTime": {"$": (activity.ended_at or activity.started_at).isoformat() + "Z", "type": "xsd:dateTime"},
            **{k: {"$": str(v), "type": "xsd:string"} for k, v in activity.metadata.items() if v},
        }
    
    for agent in record.agents:
        bundle["agent"][agent.id] = {
            "prov:type": {"$": agent.agent_type, "type": "xsd:string"},
            "prov:label": {"$": agent.name, "type": "xsd:string"},
            **({"provx:modelVersion": {"$": agent.model_version, "type": "xsd:string"}} if agent.model_version else {}),
            **({"provx:organization": {"$": agent.organization, "type": "xsd:string"}} if agent.organization else {}),
        }
    
    rel_counters: Dict[str, int] = {}
    
    for rel in record.relations:
        rel_type = rel["type"]
        counter = rel_counters.get(rel_type, 0)
        rel_id = f"_{rel_type}_{counter}"
        rel_counters[rel_type] = counter + 1
        
        if rel_type == "wasGeneratedBy":
            bundle["wasGeneratedBy"][rel_id] = {
                "prov:entity": rel.get("entity"),
                "prov:activity": rel.get("activity"),
                **({"prov:time": {"$": rel["time"], "type": "xsd:dateTime"}} if "time" in rel else {}),
            }
        elif rel_type == "wasDerivedFrom":
            bundle["wasDerivedFrom"][rel_id] = {
                "prov:generatedEntity": rel.get("generatedEntity"),
                "prov:usedEntity": rel.get("usedEntity"),
                **({"prov:activity": rel["activity"]} if "activity" in rel else {}),
            }
        elif rel_type == "wasAttributedTo":
            bundle["wasAttributedTo"][rel_id] = {
                "prov:entity": rel.get("entity"),
                "prov:agent": rel.get("agent"),
            }
        elif rel_type == "used":
            bundle["used"][rel_id] = {
                "prov:activity": rel.get("activity"),
                "prov:entity": rel.get("entity"),
            }
        elif rel_type == "wasAssociatedWith":
            bundle["wasAssociatedWith"][rel_id] = {
                "prov:activity": rel.get("activity"),
                "prov:agent": rel.get("agent"),
                **({"prov:hadRole": rel["role"]} if "role" in rel else {}),
            }
        elif rel_type == "wasInformedBy":
            bundle["wasInformedBy"][rel_id] = {
                "prov:informed": rel.get("informed"),
                "prov:informant": rel.get("informant"),
            }
        elif rel_type == "wasRevisionOf":
            bundle["wasRevisionOf"][rel_id] = {
                "prov:newerEntity": rel.get("newerEntity"),
                "prov:olderEntity": rel.get("olderEntity"),
            }

    return doc


def _agent_role(method: TranslationMethod) -> str:
    roles = {
        TranslationMethod.AI: "provx:AITranslator",
        TranslationMethod.HUMAN: "prov:Person",
        TranslationMethod.HYBRID: "provx:HybridTranslator",
    }
    return roles.get(method, "prov:Agent")


def _build_summary(
    unit: TranslationUnit,
    agent: ProvenanceAgent,
    deployments: List[DeploymentRecord],
) -> str:
    method_label = {
        TranslationMethod.AI: f"AI ({agent.name})",
        TranslationMethod.HUMAN: f"Human translator ({agent.name})",
        TranslationMethod.HYBRID: f"AI + Human post-edit ({agent.name})",
    }.get(unit.translation_method, agent.name)
    
    dep_summary = ""
    if deployments:
        contexts = list({d.context.value for d in deployments})
        locations = [d.location for d in deployments[:3]]
        dep_summary = (
            f" Deployed in {len(deployments)} location(s) "
            f"({', '.join(contexts)}): {', '.join(locations)}."
        )
    
    conf_str = f" Confidence: {unit.confidence_score:.0%}." if unit.confidence_score else ""
    return (
        f'"{unit.source_text[:60]}..." translated from {unit.source_language} '
        f"to {unit.target_language} by {method_label} "
        f"on {(unit.translated_at or datetime.utcnow()).strftime('%Y-%m-%d %H:%M UTC')}."
        f"{dep_summary}"
        f" Status: {unit.status.value}."
        f"{conf_str}"
    )
