"""Phase 13, §9b.1 — TMX import. Distinct from app/xliff/: TMX (Translation
Memory eXchange, the LISA/OSCAR vendor-exchange standard) is an older,
still-common format most enterprise localization vendors hand back
alongside or instead of XLIFF. Seeds app.core.db.models.TranslationExemplarRow
(retrieval context, not live TranslationUnits — vendor TM isn't this
system's own actively-managed translation, see tmx_import.py's docstring)
so a customer's years of vendor-approved terminology become retrieval
context without this system needing to "own" that content as if it
originated here.
"""
