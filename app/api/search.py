"""Search API - Haystack-powered semantic search over translations."""

from fastapi import APIRouter, Query
from typing import Optional
from app.models.schemas import TranslationMethod, DeploymentContext
from app.core.haystack_pipeline import search_translations, get_document_count

router = APIRouter()


@router.get("/")
async def search(
    q: str = Query(..., description="Search query"),
    source_language: Optional[str] = Query(None),
    target_language: Optional[str] = Query(None),
    method: Optional[TranslationMethod] = Query(None),
    context: Optional[DeploymentContext] = Query(None),
    semantic: bool = Query(True, description="Use semantic (embedding) search vs BM25 keyword"),
    top_k: int = Query(10, ge=1, le=50),
):
    """
    Semantic search over all indexed translations using Haystack.
    
    Supports filtering by language pair, translation method, and deployment context.
    Toggle between semantic (embedding-based) and keyword (BM25) search.
    """
    filters = {}
    if source_language:
        filters["source_language"] = source_language
    if target_language:
        filters["target_language"] = target_language
    if method:
        filters["translation_method"] = method.value
    
    results = await search_translations(
        query=q,
        filters=filters or None,
        top_k=top_k,
        use_semantic=semantic,
    )
    
    # Filter by context post-retrieval (stored as list in meta)
    if context:
        results = [
            r for r in results
            if context.value in (r.get("deployment_contexts") or [])
        ]
    
    return {
        "query": q,
        "total": len(results),
        "search_type": "semantic" if semantic else "bm25",
        "indexed_documents": get_document_count(),
        "results": results,
    }


@router.get("/indexed-count")
async def indexed_count():
    return {"indexed_documents": get_document_count()}
