"""Tests for TMX import (app/tm/tmx_import.py, §9b.1 of
docs/graphrag-provenance-proposal.md) — parses <tu>/<tuv> pairs into
TranslationExemplar rows (retrieval context), not TranslationUnits, and
tags the vendor's identity via ProvenanceAgent.organization.
Run with: PYTHONPATH=. pytest tests/test_tmx_import.py -v
"""

import pytest

from app.core.database import get_db, init_db
from app.core.graph.retrieval import retrieve_style_context
from app.models.schemas import ExemplarOrigin
from app.tm.tmx_import import import_tmx

SAMPLE_TMX = """<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="TestVendorTMS" creationtoolversion="1.0" segtype="sentence"
          o-tmf="TestVendorTMS" adminlang="en-US" srclang="en-US" datatype="plaintext"/>
  <body>
    <tu>
      <tuv xml:lang="en-US"><seg>Welcome to our platform.</seg></tuv>
      <tuv xml:lang="fr-FR"><seg>Bienvenue sur notre plateforme.</seg></tuv>
    </tu>
    <tu>
      <tuv xml:lang="en-US"><seg>Your workspace is ready.</seg></tuv>
      <tuv xml:lang="fr-FR"><seg>Votre espace de travail est pret.</seg></tuv>
    </tu>
    <tu>
      <tuv xml:lang="en-US"><seg>English only, no French pair here.</seg></tuv>
      <tuv xml:lang="de-DE"><seg>Nur auf Englisch, kein franzoesisches Paar hier.</seg></tuv>
    </tu>
  </body>
</tmx>
"""


@pytest.mark.asyncio
async def test_import_tmx_creates_exemplars_and_tags_vendor():
    await init_db()
    db = get_db()

    exemplars = await import_tmx(
        SAMPLE_TMX, source_language="en-US", target_language="fr-FR", source_system="TestVendorTMS",
    )

    # Only the two <tu> with BOTH an en-US and fr-FR <tuv> count — the
    # third (en-US/de-DE) is correctly skipped.
    assert len(exemplars) == 2
    assert {e.source_text for e in exemplars} == {
        "Welcome to our platform.", "Your workspace is ready.",
    }
    assert all(e.origin == ExemplarOrigin.VENDOR for e in exemplars)
    assert all(e.origin_agent_id for e in exemplars)

    agent = await db.get_agent(exemplars[0].origin_agent_id)
    assert agent.organization == "TestVendorTMS"
    assert agent.name == "vendor:TestVendorTMS"


@pytest.mark.asyncio
async def test_import_tmx_rejects_document_with_no_matching_pairs():
    await init_db()
    with pytest.raises(ValueError):
        await import_tmx(SAMPLE_TMX, source_language="en-US", target_language="ja-JP", source_system="TestVendorTMS")


@pytest.mark.asyncio
async def test_import_tmx_rejects_malformed_xml():
    await init_db()
    with pytest.raises(ValueError):
        await import_tmx("not xml at all <<<", source_language="en-US", target_language="fr-FR", source_system="x")


@pytest.mark.asyncio
async def test_imported_exemplars_are_retrievable_as_context():
    """The actual point of TMX import (§9b.1): imported vendor TM shows up
    in retrieve_style_context's exemplars, grounding future AI translation
    in the customer's own prior-approved work."""
    await init_db()

    await import_tmx(
        SAMPLE_TMX, source_language="en-US", target_language="fr-FR", source_system="TestVendorTMS2",
    )

    result = await retrieve_style_context("Welcome to our platform.", "en-US", "fr-FR")
    exemplar_texts = " ".join(f.text for f in result.exemplars)
    assert "Bienvenue" in exemplar_texts
