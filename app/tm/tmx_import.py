"""TMX 1.4 import — parses <tu>/<tuv> translation-memory pairs into
TranslationExemplar rows (retrieval context for app/core/graph/retrieval.py),
NOT TranslationUnits. Deliberate: a vendor's translation memory is prior,
externally-produced work being used as CONTEXT for this system's own
translations, not content this system is now responsible for tracking the
full provenance/review/redrive lifecycle of the way a native or
XLIFF-imported unit is (see app/xliff/xliff_import.py for that case).

Every exemplar is attributed to a "vendor:{source_system}" Organization
agent — ProvenanceAgent.organization carries the vendor's identity so
Phase 14's vendor scorecard can aggregate scores by it later (see
docs/graphrag-provenance-proposal.md §9b.2).
"""

import xml.etree.ElementTree as ET
from typing import List, Optional

from app.core.database import get_db
from app.core.graph import constants as gc
from app.core.graph.embeddings import embed_text
from app.models.schemas import ExemplarOrigin, TranslationExemplar

XML_NS = "{http://www.w3.org/XML/1998/namespace}"


def _primary_subtag(lang: str) -> str:
    return (lang or "").split("-")[0].lower()


def _lang_matches(tuv_lang: str, wanted_lang: str) -> bool:
    return _primary_subtag(tuv_lang) == _primary_subtag(wanted_lang)


def _seg_text(tuv_el: ET.Element) -> Optional[str]:
    seg = tuv_el.find("seg")
    if seg is None or not (seg.text or "").strip():
        return None
    return seg.text.strip()


async def import_tmx(
    xml_content: str,
    source_language: str,
    target_language: str,
    source_system: str,
    style_guide_id: Optional[str] = None,
) -> List[TranslationExemplar]:
    """Extracts the (source_language, target_language) pair from every <tu>
    that has both — a <tu> can carry more languages than that; anything
    else is ignored. Raises ValueError on malformed XML or zero usable
    pairs, same failure shape as app/xliff/xliff_import.import_xliff."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid TMX XML: {exc}") from exc

    body = root.find("body")
    if body is None:
        raise ValueError("No <body> element found in the supplied TMX document")

    db = get_db()
    vendor_agent = await db.get_or_create_agent(
        name=f"vendor:{source_system}",
        agent_type="Organization",
        organization=source_system,
        metadata={"role": "tmx_import_source"},
    )

    exemplars: List[TranslationExemplar] = []
    for tu in body.findall("tu"):
        src_text = tgt_text = None
        for tuv in tu.findall("tuv"):
            lang = tuv.get(f"{XML_NS}lang") or tuv.get("lang") or ""
            if src_text is None and _lang_matches(lang, source_language):
                src_text = _seg_text(tuv)
            if tgt_text is None and _lang_matches(lang, target_language):
                tgt_text = _seg_text(tuv)
        if not src_text or not tgt_text:
            continue

        exemplar = TranslationExemplar(
            source_text=src_text, target_text=tgt_text,
            source_language=source_language, target_language=target_language,
            origin=ExemplarOrigin.VENDOR, origin_agent_id=vendor_agent.id,
            style_guide_id=style_guide_id,
            metadata={"import_source": source_system},
        )
        embedding = await embed_text(src_text)
        await db.save_translation_exemplar(exemplar, embedding=embedding)

        exemplar_node = await db.upsert_graph_node(
            gc.NODE_EXEMPLAR, "translation_exemplars", exemplar.id,
        )
        if style_guide_id:
            guide_node = await db.upsert_graph_node(gc.NODE_STYLE_GUIDE, "style_guides", style_guide_id)
            await db.upsert_graph_edge(exemplar_node.id, guide_node.id, gc.EDGE_EXEMPLIFIES)

        exemplars.append(exemplar)

    if not exemplars:
        raise ValueError(
            f"No <tu> found with both a {source_language} and {target_language} <tuv> segment"
        )

    return exemplars
