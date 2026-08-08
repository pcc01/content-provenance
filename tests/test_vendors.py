"""Tests for Phase 14's vendor/agent scorecard
(app/core/db/repository.py's get_vendor_scorecard, app/api/vendors.py,
app/core/vendors/report.py).
Run with: PYTHONPATH=. pytest tests/test_vendors.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.models.schemas import (
    QualityScore,
    StyleAdherenceScore,
    TranslationMethod,
    TranslationUnit,
)


async def _make_scored_unit(db, agent_id, quality, tone, voice, terminology, suffix):
    unit = TranslationUnit(
        source_id=f"src-vendor-{suffix}", source_text="Some copy.", source_language="en-US",
        target_text="Une copie.", target_language="fr-FR",
        translation_method=TranslationMethod.AI, translated_by_agent_id=agent_id,
    )
    await db.save_translation_unit(unit)
    await db.save_quality_score(QualityScore(unit_id=unit.id, score=quality, scorer="stub"))
    overall = round((tone + voice + terminology) / 3, 2)
    await db.save_style_adherence_score(StyleAdherenceScore(
        unit_id=unit.id, tone_score=tone, voice_score=voice, terminology_score=terminology,
        overall_score=overall, scorer="stub",
    ))
    return unit


@pytest.mark.asyncio
async def test_vendor_scorecard_aggregates_latest_scores_by_organization():
    await init_db()
    db = get_db()

    vendor_a = await db.get_or_create_agent("vendor:ScorecardVendorA", "Organization", organization="ScorecardVendorA")
    vendor_b = await db.get_or_create_agent("vendor:ScorecardVendorB", "Organization", organization="ScorecardVendorB")

    await _make_scored_unit(db, vendor_a.id, 90, 90, 90, 90, "a1")
    await _make_scored_unit(db, vendor_a.id, 80, 80, 80, 80, "a2")
    await _make_scored_unit(db, vendor_b.id, 50, 40, 40, 40, "b1")

    scorecard = await db.get_vendor_scorecard()
    by_org = {e.organization: e for e in scorecard}

    assert by_org["ScorecardVendorA"].unit_count == 2
    assert by_org["ScorecardVendorA"].avg_quality_score == pytest.approx(85.0)
    assert by_org["ScorecardVendorB"].unit_count == 1
    assert by_org["ScorecardVendorB"].avg_quality_score == pytest.approx(50.0)

    # Ranked best-first by quality.
    org_order = [e.organization for e in scorecard if e.organization in ("ScorecardVendorA", "ScorecardVendorB")]
    assert org_order.index("ScorecardVendorA") < org_order.index("ScorecardVendorB")


@pytest.mark.asyncio
async def test_vendor_scorecard_uses_only_latest_score_per_unit():
    """A unit re-scored (e.g. after a redrive) must count once, at its
    LATEST score — not average across its whole scoring history."""
    await init_db()
    db = get_db()

    vendor = await db.get_or_create_agent("vendor:RescoredVendor", "Organization", organization="RescoredVendor")
    unit = await _make_scored_unit(db, vendor.id, 20, 20, 20, 20, "rescored")
    # A later, better score for the SAME unit.
    await db.save_quality_score(QualityScore(unit_id=unit.id, score=95, scorer="stub"))

    scorecard = await db.get_vendor_scorecard()
    entry = next(e for e in scorecard if e.organization == "RescoredVendor")
    assert entry.unit_count == 1
    assert entry.avg_quality_score == pytest.approx(95.0)  # not (20+95)/2


@pytest.mark.asyncio
async def test_vendor_scorecard_target_language_filter():
    await init_db()
    db = get_db()

    vendor = await db.get_or_create_agent("vendor:LangFilterVendor", "Organization", organization="LangFilterVendor")
    unit = TranslationUnit(
        source_id="src-lang-filter", source_text="Hi.", source_language="en-US",
        target_text="Hola.", target_language="es-ES",
        translation_method=TranslationMethod.AI, translated_by_agent_id=vendor.id,
    )
    await db.save_translation_unit(unit)
    await db.save_quality_score(QualityScore(unit_id=unit.id, score=77, scorer="stub"))

    scorecard_es = await db.get_vendor_scorecard(target_language="es-ES")
    assert any(e.organization == "LangFilterVendor" for e in scorecard_es)

    scorecard_fr = await db.get_vendor_scorecard(target_language="fr-FR")
    assert not any(e.organization == "LangFilterVendor" for e in scorecard_fr)


@pytest.mark.asyncio
async def test_vendor_scorecard_api_json_and_pdf(client):
    """Creating a translation registers the "Anthropic" agent (see
    app/core/database.py's seed) as an organization even under the mock
    backend — enough to exercise both endpoints without a real API key."""
    r = await client.post("/api/v1/translations/", json={
        "source_text": "Sign up now.", "source_language": "en-US", "target_language": "fr-FR",
        "method": "ai", "context": "website",
    })
    assert r.status_code == 201

    r = await client.get("/api/v1/vendors/scorecard")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = await client.get("/api/v1/vendors/scorecard/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
