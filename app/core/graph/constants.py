"""Node/edge type string vocabulary for the graph_nodes/graph_edges tables.
Plain string constants rather than a DB-level enum, matching how
SiteAuditCheck/finding_type etc. are handled elsewhere in this codebase —
new types don't need a migration."""

# ── Node types ───────────────────────────────────────────────────────────
NODE_UNIT = "Unit"
NODE_STYLE_GUIDE = "StyleGuide"
NODE_STYLE_GUIDE_RULE = "StyleGuideRule"
NODE_GLOSSARY_TERM = "GlossaryTerm"
NODE_EXEMPLAR = "TranslationExemplar"

# ── Edge types ───────────────────────────────────────────────────────────
EDGE_APPLIED_RULE = "appliedRule"       # Unit -> StyleGuideRule
EDGE_USED_TERM = "usedTerm"             # Unit -> GlossaryTerm
EDGE_PART_OF = "partOf"                 # StyleGuideRule/GlossaryTerm -> StyleGuide
EDGE_PREFERRED_OVER = "preferredOver"   # GlossaryTerm -> GlossaryTerm (deprecated alternative)
EDGE_EXEMPLIFIES = "exemplifies"        # TranslationExemplar -> StyleGuide
