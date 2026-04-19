"""
AI Translation Provenance System
FastAPI application with Haystack integration, XLIFF support, and W3C PROV-DM compliance.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
import uvicorn

from app.api import translations, provenance, search, xliff_export
from app.core.database import init_db
from app.core.haystack_pipeline import init_haystack


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_haystack()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="AI Translation Provenance System",
    description="""
    A comprehensive provenance tracking system for AI-translated content.
    
    Features:
    - Full W3C PROV-DM compliant provenance tracking
    - XLIFF 2.0 standard translation format support
    - Haystack-powered semantic search over translation history
    - Multi-context tracking (website, banner ad, marketing campaign, etc.)
    - Human vs AI translation differentiation
    - Complete audit trail for all translation activities
    """,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(translations.router, prefix="/api/v1/translations", tags=["Translations"])
app.include_router(provenance.router, prefix="/api/v1/provenance", tags=["Provenance"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])
app.include_router(xliff_export.router, prefix="/api/v1/xliff", tags=["XLIFF"])


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "AI Translation Provenance System"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
