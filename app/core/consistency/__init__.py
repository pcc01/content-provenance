"""Phase 14 — cross-document/page tone & terminology consistency check.

Deliberately NOT wired into app/core/audit/'s SiteAuditCheck framework:
that subsystem audits crawled THIRD-PARTY site HTML (a SiteAudit's
root_url, SiteAuditPage's crawled text) — a different data domain from
this system's OWN TranslationUnits. This module instead clusters units by
the GlossaryTerm/StyleGuideRule graph_edges Phase 13 already populates,
using the O(k·n) technique from Barry et al. 2025 (§7 of
docs/graphrag-provenance-proposal.md) rather than an O(n²) full pairwise
scan. See checker.py.
"""
