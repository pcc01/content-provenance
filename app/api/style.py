"""Phase 13 — Style Guides / Glossary API: CRUD for the structured facts
app/core/graph/retrieval.py retrieves, plus the source-language voice check
(§9b.5 of docs/graphrag-provenance-proposal.md — score a DRAFT before
translation even happens, not just a translated unit after the fact)."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_db
from app.core.graph import builder as graph_builder
from app.core.graph.embeddings import embed_text
from app.core.graph.retrieval import retrieve_style_context
from app.core.scoring.style_base import StyleScoreResult
from app.core.scoring.style_factory import get_style_scorer
from app.models.schemas import (
    CheckSourceRequest,
    CheckSourceResponse,
    CreateGlossaryTermRequest,
    CreateStyleGuideRequest,
    CreateStyleGuideRuleRequest,
    GlossaryTerm,
    StyleGuide,
    StyleGuideRule,
)

router = APIRouter()


# ── Style Guides ─────────────────────────────────────────────────────────

@router.post("/guides", response_model=StyleGuide, status_code=201)
async def create_style_guide(request: CreateStyleGuideRequest):
    db = get_db()
    guide = StyleGuide(
        name=request.name, version=request.version, locale=request.locale,
        voice_description=request.voice_description, tone_attributes=request.tone_attributes,
        supersedes_id=request.supersedes_id, created_by=request.created_by,
    )
    await db.save_style_guide(guide)
    await graph_builder.ensure_style_guide_node(guide.id, label=f"{guide.name} v{guide.version}")
    return guide


@router.get("/guides", response_model=list[StyleGuide])
async def list_style_guides(locale: Optional[str] = Query(None)):
    db = get_db()
    return await db.list_style_guides(locale=locale)


@router.get("/guides/{guide_id}", response_model=StyleGuide)
async def get_style_guide(guide_id: str):
    db = get_db()
    guide = await db.get_style_guide(guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail=f"Style guide {guide_id} not found")
    return guide


@router.get("/guides/{guide_id}/chain", response_model=list[StyleGuide])
async def get_style_guide_chain(guide_id: str):
    """Walks the supersedes_id chain back to the oldest ancestor — see
    StyleGuideRow's docstring and §3b of the proposal doc."""
    db = get_db()
    if not await db.get_style_guide(guide_id):
        raise HTTPException(status_code=404, detail=f"Style guide {guide_id} not found")
    return await db.get_style_guide_chain(guide_id)


# ── Style Guide Rules ────────────────────────────────────────────────────

@router.post("/guides/{guide_id}/rules", response_model=StyleGuideRule, status_code=201)
async def create_style_guide_rule(guide_id: str, request: CreateStyleGuideRuleRequest):
    db = get_db()
    if not await db.get_style_guide(guide_id):
        raise HTTPException(status_code=404, detail=f"Style guide {guide_id} not found")

    rule = StyleGuideRule(
        style_guide_id=guide_id, rule_type=request.rule_type, rule_text=request.rule_text,
        severity=request.severity, applies_to_locale=request.applies_to_locale,
        source_term=request.source_term, target_term=request.target_term,
    )
    embedding = await embed_text(rule.rule_text)
    await db.save_style_guide_rule(rule, embedding=embedding)
    await graph_builder.link_rule_to_guide(rule.id, guide_id, label=rule.rule_text[:60])
    return rule


@router.get("/guides/{guide_id}/rules", response_model=list[StyleGuideRule])
async def list_style_guide_rules(guide_id: str, locale: Optional[str] = Query(None)):
    db = get_db()
    return await db.list_style_guide_rules(style_guide_id=guide_id, locale=locale)


# ── Glossary Terms ───────────────────────────────────────────────────────

@router.post("/glossary-terms", response_model=GlossaryTerm, status_code=201)
async def create_glossary_term(request: CreateGlossaryTermRequest):
    db = get_db()
    if request.style_guide_id and not await db.get_style_guide(request.style_guide_id):
        raise HTTPException(status_code=404, detail=f"Style guide {request.style_guide_id} not found")

    term = GlossaryTerm(
        style_guide_id=request.style_guide_id, source_term=request.source_term,
        target_term=request.target_term, locale=request.locale,
        do_not_translate=request.do_not_translate, notes=request.notes,
    )
    embedding = await embed_text(term.source_term)
    await db.save_glossary_term(term, embedding=embedding)
    await graph_builder.link_term_to_guide(term.id, request.style_guide_id, label=term.source_term)
    if request.preferred_over_term_ids:
        await graph_builder.link_preferred_over(term.id, request.preferred_over_term_ids)
    return term


@router.get("/glossary-terms", response_model=list[GlossaryTerm])
async def list_glossary_terms(
    style_guide_id: Optional[str] = Query(None), locale: Optional[str] = Query(None),
):
    db = get_db()
    return await db.list_glossary_terms(style_guide_id=style_guide_id, locale=locale)


# ── Retrieval preview (debugging/admin visibility) ──────────────────────

@router.get("/retrieve-preview")
async def retrieve_preview(
    text: str = Query(..., min_length=1),
    source_language: str = Query(...),
    target_language: str = Query(...),
    style_guide_id: Optional[str] = Query(None),
):
    """What app/core/graph/retrieval.py would hand the LLM for this source
    text right now — the same call site translations.py's create endpoint
    and the redrive engine make, exposed read-only so a style-guide admin
    can verify retrieval is picking up the right rules/terms before it
    starts shaping real translations."""
    retrieval = await retrieve_style_context(text, source_language, target_language, style_guide_id=style_guide_id)
    return {
        "rules": [f.model_dump() for f in retrieval.rules],
        "terms": [f.model_dump() for f in retrieval.terms],
        "exemplars": [f.model_dump() for f in retrieval.exemplars],
        "prompt_context": retrieval.as_prompt_context(),
    }


# ── Source-language voice check (§9b.5) ─────────────────────────────────

@router.post("/check-source", response_model=CheckSourceResponse)
async def check_source(request: CheckSourceRequest):
    """Scores a DRAFT against style/voice rules BEFORE translation even
    happens — catching an off-brand source draft is cheaper than catching
    it after it's been translated into a dozen languages (§9b.5). Does not
    persist a StyleAdherenceScore row (there's no TranslationUnit to attach
    one to) — this is a pre-check, not part of the redrive threshold loop."""
    context = await retrieve_style_context(
        request.text, request.language, request.language, style_guide_id=request.style_guide_id,
    )
    scorer = get_style_scorer()
    try:
        result = await scorer.score_text(request.text, request.language, context)
    except Exception as e:
        # Same resilience app/core/scoring/style_factory.score_unit_style
        # already applies — a scorer outage shouldn't 500 a quick
        # pre-translation check, it should come back flagged for review.
        result = StyleScoreResult(reasons=["scorer_error"], raw_response=str(e), needs_review=True)
    return CheckSourceResponse(
        tone_score=result.tone_score, voice_score=result.voice_score,
        overall_score=result.overall_score, reasons=result.reasons,
        style_guide_id=request.style_guide_id, needs_review=result.needs_review,
    )
