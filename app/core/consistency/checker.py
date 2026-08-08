"""Phase 14 — the actual consistency-check algorithm. See this package's
docstring for why it's separate from app/core/audit/.

Two checks, both built by clustering units around a shared graph_edges
neighbor (a GlossaryTerm or a StyleGuideRule) rather than comparing every
unit against every other unit:

  terminology — for each GlossaryTerm with units attached via `usedTerm`
  edges, check whether each unit's target_text actually contains the
  term's expected rendering (target_term, or the source_term verbatim for
  do-not-translate terms). A cluster with a MIX of compliant/non-compliant
  units is a genuine inconsistency (the same term rendered two ways); a
  cluster where none comply is systemic drift — reported as two distinct
  finding_types since they call for different fixes (one unit vs. the
  term/rule itself).

  tone — for each StyleGuideRule with 2+ units attached via `appliedRule`
  edges, compare their latest style_adherence_scores.tone_score; a wide
  spread within one cluster means the same rule is landing very
  differently across units that are all supposed to follow it.
"""

from typing import Any, Dict, List

from app.core.database import get_db
from app.models.schemas import ConsistencyCheckResult, ConsistencyFinding

TONE_SPREAD_THRESHOLD = 25.0  # 0-100 scale, same convention as quality/style scores


async def run_consistency_check(scope: Dict[str, Any]) -> ConsistencyCheckResult:
    db = get_db()
    units = await db.list_units_by_scope(scope)
    unit_by_id = {u.id: u for u in units}
    findings: List[ConsistencyFinding] = []

    term_clusters, rule_clusters = await _build_clusters(units)
    findings.extend(await _check_terminology(term_clusters, unit_by_id))
    findings.extend(await _check_tone_spread(rule_clusters))

    return ConsistencyCheckResult(scope=scope, units_checked=len(units), findings=findings)


async def _build_clusters(units) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """One graph lookup per unit (O(n)), not one comparison per PAIR of
    units (O(n²)) — the actual complexity win this module exists for."""
    db = get_db()
    term_clusters: Dict[str, List[str]] = {}
    rule_clusters: Dict[str, List[str]] = {}
    for unit in units:
        node = await db.get_graph_node("Unit", unit.id)
        if node is None:
            continue
        for term_node in await db.list_neighbors(node.id, edge_type="usedTerm", direction="out"):
            term_clusters.setdefault(term_node.ref_id, []).append(unit.id)
        for rule_node in await db.list_neighbors(node.id, edge_type="appliedRule", direction="out"):
            rule_clusters.setdefault(rule_node.ref_id, []).append(unit.id)
    return term_clusters, rule_clusters


async def _check_terminology(
    term_clusters: Dict[str, List[str]], unit_by_id: Dict[str, Any],
) -> List[ConsistencyFinding]:
    db = get_db()
    findings: List[ConsistencyFinding] = []
    for term_id, unit_ids in term_clusters.items():
        term = await db.get_glossary_term(term_id)
        if term is None:
            continue

        compliant, drifted = [], []
        for uid in unit_ids:
            unit = unit_by_id.get(uid)
            if unit is None or not unit.target_text:
                continue
            text_lower = unit.target_text.lower()
            if term.do_not_translate:
                ok = term.source_term.lower() in text_lower
            elif term.target_term:
                ok = term.target_term.lower() in text_lower
            else:
                continue  # nothing concrete configured to check against
            (compliant if ok else drifted).append(uid)

        if not drifted:
            continue
        finding_type = "term_inconsistency" if compliant else "term_drift"
        expected = "kept as-is" if term.do_not_translate else f"'{term.target_term}'"
        findings.append(ConsistencyFinding(
            finding_type=finding_type,
            severity="warning" if finding_type == "term_inconsistency" else "info",
            summary=(
                f"'{term.source_term}' should be {expected}, but {len(drifted)} of "
                f"{len(unit_ids)} unit(s) using this term don't match"
                + (f" ({len(compliant)} do)" if compliant else "")
            ),
            unit_ids=drifted,
            detail={
                "term_id": term_id, "source_term": term.source_term,
                "target_term": term.target_term, "compliant_unit_ids": compliant,
            },
        ))
    return findings


async def _check_tone_spread(rule_clusters: Dict[str, List[str]]) -> List[ConsistencyFinding]:
    db = get_db()
    findings: List[ConsistencyFinding] = []
    for rule_id, unit_ids in rule_clusters.items():
        if len(unit_ids) < 2:
            continue
        scored = []
        for uid in unit_ids:
            score = await db.get_latest_style_adherence_score(uid)
            if score and score.tone_score is not None:
                scored.append((uid, score.tone_score))
        if len(scored) < 2:
            continue

        tones = [t for _, t in scored]
        spread = max(tones) - min(tones)
        if spread <= TONE_SPREAD_THRESHOLD:
            continue

        rule = await db.get_style_guide_rule(rule_id)
        findings.append(ConsistencyFinding(
            finding_type="tone_spread",
            severity="warning",
            summary=(
                f"Tone adherence varies by {spread:.0f} points across {len(scored)} units "
                f"applying the same rule" + (f" ('{rule.rule_text}')" if rule else "")
            ),
            unit_ids=[uid for uid, _ in scored],
            detail={"rule_id": rule_id, "tone_scores": dict(scored)},
        ))
    return findings
