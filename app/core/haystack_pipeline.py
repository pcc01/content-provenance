"""
Haystack Pipeline for Translation Provenance Search
Uses Haystack 2.x with in-memory document store and sentence-transformers embeddings.

Enables semantic search over:
- Source texts and their translations
- Provenance metadata (who translated, when, method)
- Deployment contexts and locations
"""

from typing import List, Optional, Dict, Any

# Haystack 2.x imports
try:
    from haystack import Document, Pipeline
    from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever, InMemoryBM25Retriever
    from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
    from haystack.document_stores.in_memory import InMemoryDocumentStore
    HAYSTACK_AVAILABLE = True
except ImportError:
    HAYSTACK_AVAILABLE = False

from app.models.schemas import TranslationUnit, DeploymentRecord

# Global Haystack components
_document_store: Optional[Any] = None
_indexing_pipeline: Optional[Any] = None
_search_pipeline: Optional[Any] = None
_bm25_pipeline: Optional[Any] = None


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


async def init_haystack():
    """Initialize Haystack document store and pipelines."""
    global _document_store, _indexing_pipeline, _search_pipeline, _bm25_pipeline
    
    if not HAYSTACK_AVAILABLE:
        print("⚠  Haystack not installed. Search will use fallback keyword matching.")
        return
    
    try:
        # Document store
        _document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")
        
        # Indexing pipeline (add translations to the store)
        _indexing_pipeline = Pipeline()
        doc_embedder = SentenceTransformersDocumentEmbedder(model=EMBEDDING_MODEL)
        doc_embedder.warm_up()
        _indexing_pipeline.add_component("embedder", doc_embedder)
        _indexing_pipeline.add_component("writer", _document_store.write_documents if hasattr(_document_store, 'write_documents') else None)
        
        # Search pipeline (semantic)
        _search_pipeline = Pipeline()
        text_embedder = SentenceTransformersTextEmbedder(model=EMBEDDING_MODEL)
        text_embedder.warm_up()
        retriever = InMemoryEmbeddingRetriever(document_store=_document_store)
        _search_pipeline.add_component("embedder", text_embedder)
        _search_pipeline.add_component("retriever", retriever)
        _search_pipeline.connect("embedder.embedding", "retriever.query_embedding")
        
        # BM25 fallback pipeline (keyword)
        _bm25_pipeline = Pipeline()
        bm25_retriever = InMemoryBM25Retriever(document_store=_document_store)
        _bm25_pipeline.add_component("retriever", bm25_retriever)
        
        print("✓ Haystack pipelines initialized")
    except Exception as e:
        print(f"⚠  Haystack initialization error: {e}. Using fallback search.")
        _document_store = None


def _build_haystack_document(
    unit: TranslationUnit,
    deployments: Optional[List[DeploymentRecord]] = None
) -> "Document":
    """Convert a TranslationUnit to a Haystack Document for indexing."""
    
    deployment_contexts = []
    deployment_locations = []
    if deployments:
        deployment_contexts = list({d.context.value for d in deployments})
        deployment_locations = [d.location for d in deployments]
    
    # Rich text for semantic search
    content = f"""
Source ({unit.source_language}): {unit.source_text}
Translation ({unit.target_language}): {unit.target_text or ''}
Method: {unit.translation_method.value}
Status: {unit.status.value}
Contexts: {', '.join(deployment_contexts) if deployment_contexts else 'not deployed'}
Locations: {', '.join(deployment_locations) if deployment_locations else 'none'}
    """.strip()
    
    meta = {
        "translation_unit_id": unit.id,
        "source_language": unit.source_language,
        "target_language": unit.target_language,
        "translation_method": unit.translation_method.value,
        "status": unit.status.value,
        "translated_at": unit.translated_at.isoformat() if unit.translated_at else None,
        "confidence_score": unit.confidence_score,
        "quality_score": unit.quality_score,
        "deployment_contexts": deployment_contexts,
        "deployment_locations": deployment_locations,
        "agent_id": unit.translated_by_agent_id,
        "source_text": unit.source_text,
        "target_text": unit.target_text or "",
    }
    
    if HAYSTACK_AVAILABLE:
        return Document(id=unit.id, content=content, meta=meta)
    return {"id": unit.id, "content": content, "meta": meta}


async def index_translation_unit(
    unit: TranslationUnit,
    deployments: Optional[List[DeploymentRecord]] = None
) -> bool:
    """Add or update a translation unit in the Haystack document store."""
    
    doc = _build_haystack_document(unit, deployments)
    
    if not HAYSTACK_AVAILABLE or _document_store is None:
        # Fallback: store in a simple list
        _fallback_store.append(doc)
        return True
    
    try:
        # Use the document store directly for simplicity
        # In a full Haystack 2.x setup you'd run the indexing pipeline
        embedder = SentenceTransformersDocumentEmbedder(model=EMBEDDING_MODEL)
        embedder.warm_up()
        result = embedder.run(documents=[doc])
        _document_store.write_documents(result["documents"])
        return True
    except Exception as e:
        print(f"Indexing error: {e}")
        _fallback_store.append(doc)
        return False


# Fallback store when Haystack is not available
_fallback_store: List[Dict] = []


async def search_translations(
    query: str,
    filters: Optional[Dict] = None,
    top_k: int = 10,
    use_semantic: bool = True,
) -> List[Dict[str, Any]]:
    """
    Search translations using Haystack semantic search or BM25 fallback.
    
    Returns list of results with score and metadata.
    """
    
    if not HAYSTACK_AVAILABLE or _document_store is None:
        return _fallback_keyword_search(query, filters, top_k)
    
    try:
        if use_semantic:
            results = _search_pipeline.run({
                "embedder": {"text": query},
                "retriever": {"top_k": top_k, **({"filters": filters} if filters else {})}
            })
            docs = results.get("retriever", {}).get("documents", [])
        else:
            results = _bm25_pipeline.run({
                "retriever": {"query": query, "top_k": top_k}
            })
            docs = results.get("retriever", {}).get("documents", [])
        
        return [
            {
                "translation_unit_id": doc.meta.get("translation_unit_id"),
                "score": doc.score,
                "source_text": doc.meta.get("source_text", ""),
                "target_text": doc.meta.get("target_text", ""),
                "source_language": doc.meta.get("source_language"),
                "target_language": doc.meta.get("target_language"),
                "translation_method": doc.meta.get("translation_method"),
                "status": doc.meta.get("status"),
                "deployment_contexts": doc.meta.get("deployment_contexts", []),
                "translated_at": doc.meta.get("translated_at"),
                "confidence_score": doc.meta.get("confidence_score"),
            }
            for doc in docs
        ]
    except Exception as e:
        print(f"Search error: {e}. Falling back to keyword search.")
        return _fallback_keyword_search(query, filters, top_k)


def _fallback_keyword_search(
    query: str,
    filters: Optional[Dict],
    top_k: int
) -> List[Dict[str, Any]]:
    """Simple keyword search fallback when Haystack is unavailable."""
    query_lower = query.lower()
    results = []
    
    for doc in _fallback_store:
        meta = doc.get("meta", {}) if isinstance(doc, dict) else doc.meta
        content = doc.get("content", "") if isinstance(doc, dict) else doc.content
        
        # Apply filters
        if filters:
            skip = False
            for k, v in filters.items():
                if meta.get(k) != v:
                    skip = True
                    break
            if skip:
                continue
        
        # Score by keyword overlap
        words = query_lower.split()
        content_lower = content.lower()
        score = sum(1 for w in words if w in content_lower) / max(len(words), 1)
        
        if score > 0:
            results.append({
                "translation_unit_id": meta.get("translation_unit_id"),
                "score": score,
                "source_text": meta.get("source_text", ""),
                "target_text": meta.get("target_text", ""),
                "source_language": meta.get("source_language"),
                "target_language": meta.get("target_language"),
                "translation_method": meta.get("translation_method"),
                "status": meta.get("status"),
                "deployment_contexts": meta.get("deployment_contexts", []),
                "translated_at": meta.get("translated_at"),
                "confidence_score": meta.get("confidence_score"),
            })
    
    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def get_document_count() -> int:
    """Return number of indexed documents."""
    if _document_store is not None:
        try:
            return _document_store.count_documents()
        except:
            pass
    return len(_fallback_store)
