"""
Test suite for AI Translation Provenance System
Tests models, XLIFF generation, PROV-DM builder, and API endpoints.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

# ── Test Models ───────────────────────────────────────────────────────────────

def test_translation_unit_creation():
    from app.models.schemas import TranslationUnit, TranslationMethod, TranslationStatus
    unit = TranslationUnit(
        source_id="src-001",
        source_text="Hello world",
        source_language="en-US",
        target_text="Bonjour le monde",
        target_language="fr-FR",
        translation_method=TranslationMethod.AI,
        translated_by_agent_id="agent:test",
        translated_at=datetime.utcnow(),
        confidence_score=0.95,
    )
    assert unit.source_text == "Hello world"
    assert unit.translation_method == TranslationMethod.AI
    assert unit.status == TranslationStatus.PENDING
    print("✓ TranslationUnit creation OK")


def test_deployment_record():
    from app.models.schemas import DeploymentRecord, DeploymentContext
    dep = DeploymentRecord(
        translation_unit_id="unit-001",
        context=DeploymentContext.BANNER_AD,
        location="https://ads.example.com/campaign/q4-2024",
        is_active=True,
    )
    assert dep.context == DeploymentContext.BANNER_AD
    assert dep.is_active
    print("✓ DeploymentRecord creation OK")


def test_provenance_agent_types():
    from app.models.schemas import ProvenanceAgent
    ai_agent = ProvenanceAgent(
        name="claude-3-7-sonnet",
        agent_type="SoftwareAgent",
        model_version="claude-3-7-sonnet-20250219",
        organization="Anthropic",
    )
    human_agent = ProvenanceAgent(name="Jane Smith", agent_type="Person")
    
    assert ai_agent.agent_type == "SoftwareAgent"
    assert human_agent.agent_type == "Person"
    assert "claude" in ai_agent.name
    print("✓ ProvenanceAgent types OK")


# ── Test XLIFF Generation ─────────────────────────────────────────────────────

def test_xliff_single_unit():
    from app.models.schemas import TranslationUnit, TranslationMethod
    from app.xliff.xliff_service import build_single_unit_xliff
    
    unit = TranslationUnit(
        source_id="src-001",
        source_text="Our platform delivers excellence.",
        source_language="en-US",
        target_text="Notre plateforme offre l'excellence.",
        target_language="fr-FR",
        translation_method=TranslationMethod.AI,
        translated_by_agent_id="agent:claude",
        translated_at=datetime.utcnow(),
        confidence_score=0.93,
    )
    
    xliff = build_single_unit_xliff(unit)
    
    assert '<?xml version' in xliff
    assert 'xliff' in xliff.lower()
    assert 'version="2.0"' in xliff
    assert unit.source_text in xliff
    assert unit.target_text in xliff
    assert 'en-US' in xliff
    assert 'fr-FR' in xliff
    assert 'ai' in xliff  # translation method
    assert 'prov' in xliff.lower()  # provenance namespace
    print("✓ XLIFF 2.0 generation OK")
    print(f"  Generated {len(xliff)} bytes of XLIFF")


def test_xliff_contains_prov_metadata():
    from app.models.schemas import TranslationUnit, TranslationMethod
    from app.xliff.xliff_service import build_single_unit_xliff
    
    unit = TranslationUnit(
        source_id="src-002",
        source_text="Click here to learn more.",
        source_language="en-US",
        target_text="Cliquez ici pour en savoir plus.",
        target_language="fr-FR",
        translation_method=TranslationMethod.HUMAN,
        translated_by_agent_id="agent:human-jane",
        translated_at=datetime.utcnow(),
    )
    
    xliff = build_single_unit_xliff(unit)
    
    # PROV-DM namespaces should be present
    assert 'prov' in xliff.lower()
    assert 'translation-method' in xliff
    assert 'translated-by-agent' in xliff
    print("✓ XLIFF W3C PROV metadata OK")


def test_xliff_parse_round_trip():
    from app.models.schemas import TranslationUnit, TranslationMethod
    from app.xliff.xliff_service import build_single_unit_xliff, parse_xliff_document
    
    unit = TranslationUnit(
        source_id="src-rt",
        source_text="Round trip test content.",
        source_language="en-US",
        target_text="Inhalt des Rundreise-Tests.",
        target_language="de-DE",
        translation_method=TranslationMethod.HYBRID,
        translated_by_agent_id="agent:hybrid",
        translated_at=datetime.utcnow(),
    )
    
    xliff = build_single_unit_xliff(unit)
    parsed = parse_xliff_document(xliff)
    
    assert len(parsed) == 1
    assert parsed[0]['source'] == unit.source_text
    assert parsed[0]['target'] == unit.target_text
    print("✓ XLIFF parse round-trip OK")


# ── Test W3C PROV-DM Builder ──────────────────────────────────────────────────

def test_prov_record_structure():
    """Test that provenance records have correct W3C PROV-DM structure."""
    import asyncio
    from app.core.database import init_db, get_db
    from app.models.schemas import TranslationUnit, TranslationMethod
    from app.core.prov_builder import build_provenance_record, to_prov_json
    
    asyncio.run(init_db())
    db = get_db()
    
    agent = db.get_or_create_agent("claude-3-7-sonnet", "SoftwareAgent", model_version="v1")
    
    unit = TranslationUnit(
        source_id="src-prov",
        source_text="Test provenance tracking.",
        source_language="en-US",
        target_text="Provenienz-Tracking testen.",
        target_language="de-DE",
        translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
        translated_at=datetime.utcnow(),
        confidence_score=0.88,
    )
    
    record = build_provenance_record(unit, deployments=[])
    
    # Must have at least 2 entities: source + translation
    assert len(record.entities) >= 2
    # Must have at least 1 activity: translation
    assert len(record.activities) >= 1
    # Must have at least 1 agent
    assert len(record.agents) >= 1
    # Must have relations
    assert len(record.relations) > 0
    
    # Check entity types
    entity_types = [e.entity_type for e in record.entities]
    assert "SourceText" in entity_types
    assert "Translation" in entity_types
    
    # Check activity type
    assert any(a.activity_type == "Translation" for a in record.activities)
    
    print(f"✓ PROV record: {len(record.entities)} entities, {len(record.activities)} activities, {len(record.agents)} agents, {len(record.relations)} relations")


def test_prov_json_serialization():
    """Test W3C PROV-JSON serialization."""
    import asyncio
    from app.core.database import init_db, get_db
    from app.models.schemas import TranslationUnit, TranslationMethod
    from app.core.prov_builder import build_provenance_record, to_prov_json
    
    asyncio.run(init_db())
    db = get_db()
    agent = db.get_or_create_agent("test-agent", "SoftwareAgent")
    
    unit = TranslationUnit(
        source_id="src-json",
        source_text="JSON serialization test.",
        source_language="en-US",
        target_text="Test de sérialisation JSON.",
        target_language="fr-FR",
        translation_method=TranslationMethod.AI,
        translated_by_agent_id=agent.id,
        translated_at=datetime.utcnow(),
    )
    
    record = build_provenance_record(unit)
    prov_json = to_prov_json(record)
    
    # PROV-JSON structure
    assert "prefix" in prov_json
    assert "bundle" in prov_json
    assert "prov" in prov_json["prefix"]
    assert "xsd" in prov_json["prefix"]
    
    bundle = list(prov_json["bundle"].values())[0]
    assert "entity" in bundle
    assert "activity" in bundle
    assert "agent" in bundle
    assert "wasGeneratedBy" in bundle
    assert "wasAttributedTo" in bundle
    
    print("✓ PROV-JSON serialization OK")
    print(f"  Bundle has {len(bundle['entity'])} entities, {len(bundle['agent'])} agents")


def test_prov_with_deployment():
    """Test provenance with deployment records included."""
    import asyncio
    from app.core.database import init_db, get_db
    from app.models.schemas import TranslationUnit, TranslationMethod, DeploymentRecord, DeploymentContext
    from app.core.prov_builder import build_provenance_record
    
    asyncio.run(init_db())
    db = get_db()
    agent = db.get_or_create_agent("test-agent-2", "SoftwareAgent")
    
    unit = TranslationUnit(
        source_id="src-dep",
        source_text="Deployed content test.",
        source_language="en-US",
        target_text="Test de contenu déployé.",
        target_language="fr-FR",
        translation_method=TranslationMethod.HYBRID,
        translated_by_agent_id=agent.id,
        translated_at=datetime.utcnow(),
    )
    
    dep = DeploymentRecord(
        translation_unit_id=unit.id,
        context=DeploymentContext.BANNER_AD,
        location="https://cdn.ads.example.com/banner/001",
        deployed_at=datetime.utcnow(),
    )
    
    record = build_provenance_record(unit, deployments=[dep])
    
    # Should have deployment entity and activity
    entity_types = [e.entity_type for e in record.entities]
    assert "DeployedContent" in entity_types
    
    activity_types = [a.activity_type for a in record.activities]
    assert "Publication" in activity_types
    
    print("✓ PROV with deployment records OK")


# ── Test Database Layer ───────────────────────────────────────────────────────

def test_database_crud():
    import asyncio
    from app.core.database import init_db, get_db
    from app.models.schemas import TranslationUnit, TranslationMethod
    
    asyncio.run(init_db())
    db = get_db()
    
    agent = db.get_or_create_agent("test-db-agent", "Person")
    
    unit = TranslationUnit(
        source_id="src-db",
        source_text="Database CRUD test.",
        source_language="en-US",
        target_text="Test CRUD de base de données.",
        target_language="fr-FR",
        translation_method=TranslationMethod.HUMAN,
        translated_by_agent_id=agent.id,
        translated_at=datetime.utcnow(),
    )
    db.save_translation_unit(unit)
    
    retrieved = db.get_translation_unit(unit.id)
    assert retrieved is not None
    assert retrieved.source_text == unit.source_text
    
    # Test listing
    units = db.list_translation_units(source_language="en-US")
    assert any(u.id == unit.id for u in units)
    
    print("✓ Database CRUD OK")


# ── Test Runner ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_translation_unit_creation,
        test_deployment_record,
        test_provenance_agent_types,
        test_xliff_single_unit,
        test_xliff_contains_prov_metadata,
        test_xliff_parse_round_trip,
        test_prov_record_structure,
        test_prov_json_serialization,
        test_prov_with_deployment,
        test_database_crud,
    ]
    
    passed = 0
    failed = 0
    
    print("\n" + "="*60)
    print("  AI TRANSLATION PROVENANCE SYSTEM - TEST SUITE")
    print("="*60 + "\n")
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed:
        exit(1)
