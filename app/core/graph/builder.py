"""Write-path helpers keeping graph_nodes/graph_edges in sync with the
style guide/rule/glossary-term/unit tables they mirror. Thin orchestration
over app/core/db/repository.py's graph methods — this module decides
WHICH nodes/edges a given write implies, the repository owns the actual
SQL.
"""

from typing import List, Optional

from app.core.database import get_db
from app.core.graph import constants as gc
from app.models.schemas import StyleContextRetrieval, StyleGuideRule


async def ensure_style_guide_node(style_guide_id: str, label: Optional[str] = None):
    db = get_db()
    return await db.upsert_graph_node(gc.NODE_STYLE_GUIDE, "style_guides", style_guide_id, label=label)


async def link_rule_to_guide(rule_id: str, style_guide_id: str, label: Optional[str] = None) -> None:
    db = get_db()
    guide_node = await ensure_style_guide_node(style_guide_id)
    rule_node = await db.upsert_graph_node(gc.NODE_STYLE_GUIDE_RULE, "style_guide_rules", rule_id, label=label)
    await db.upsert_graph_edge(rule_node.id, guide_node.id, gc.EDGE_PART_OF)


async def link_term_to_guide(term_id: str, style_guide_id: Optional[str], label: Optional[str] = None) -> None:
    db = get_db()
    term_node = await db.upsert_graph_node(gc.NODE_GLOSSARY_TERM, "glossary_terms", term_id, label=label)
    if style_guide_id:
        guide_node = await ensure_style_guide_node(style_guide_id)
        await db.upsert_graph_edge(term_node.id, guide_node.id, gc.EDGE_PART_OF)


async def link_preferred_over(term_id: str, alternative_term_ids: List[str]) -> None:
    db = get_db()
    for alt_id in alternative_term_ids:
        await db.link_glossary_preferred_over(term_id, alt_id)


async def sibling_rules(
    style_guide_id: str, exclude_rule_id: Optional[str] = None, limit: int = 5,
) -> List[StyleGuideRule]:
    """The "also pull every rule in the same style-guide section" step from
    §4 Option 1 of the proposal doc — a plain FK join on style_guide_id
    (not graph_edges: style_guide_id is already a direct column on
    style_guide_rules, so this specific hop needs no graph traversal at
    all, per §3d's "where plain tables are just as good")."""
    db = get_db()
    rules = await db.list_style_guide_rules(style_guide_id=style_guide_id, limit=limit + 1)
    return [r for r in rules if r.id != exclude_rule_id][:limit]


async def record_unit_style_context(unit_id: str, retrieval: StyleContextRetrieval) -> None:
    """Records which rules/terms a unit's retrieved context actually
    included as graph_edges — the data Phase 14's cross-document
    consistency check clusters units by (§7 of the proposal doc). Called
    once retrieval has actually been used for a real translation, not on
    every speculative retrieve_style_context() call."""
    db = get_db()
    rule_ids = [f.id for f in retrieval.rules]
    term_ids = [f.id for f in retrieval.terms]
    if rule_ids or term_ids:
        await db.link_unit_style_context(unit_id, rule_ids, term_ids)
