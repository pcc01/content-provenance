"""Phase 13 — pgGraph: the graph layer over style guides, glossary terms,
translation exemplars, and translation units. Plain relational tables
(graph_nodes/graph_edges in app/core/db/models.py), not Apache AGE — see
docs/graphrag-provenance-proposal.md §3 for why.

  constants.py   — node_type / edge_type string vocabulary
  embeddings.py  — lazy sentence-transformers wrapper (degrades gracefully
                   when the package/model isn't available, same pattern as
                   app/core/haystack_pipeline.py's HAYSTACK_AVAILABLE)
  builder.py     — write-path helpers: keep graph_nodes/edges in sync when
                   style guides/rules/terms are created
  retrieval.py   — retrieve_style_context(): the hybrid vector+graph
                   retrieval this whole phase is for
"""
