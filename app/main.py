"""
AI Translation Provenance System
FastAPI application with Haystack integration, XLIFF support, and W3C PROV-DM compliance.
"""

import sys

# Several startup log lines use non-ASCII characters (checkmarks); Windows'
# default console codepage (cp1252) can't encode them and would otherwise
# crash the app before it ever binds a port. Docker/Linux consoles are UTF-8
# already, so this is a no-op there.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
import uvicorn

from app.api import (
    translations, provenance, search, xliff_export, xliff_import, redrive, images,
    notes, documents, pages, audit, style, tm, vendors, consistency, quality, models,
    json_export, json_import, integrations,
)
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
app.include_router(notes.router, prefix="/api/v1/translations", tags=["Notes"])
app.include_router(provenance.router, prefix="/api/v1/provenance", tags=["Provenance"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])
# xliff_import mounted BEFORE xliff_export under the same prefix: its literal
# routes (/import, /ingest-log) must be matched before xliff_export's
# catch-all /{unit_id} route, which would otherwise treat "import" as a
# unit_id — route registration order is what decides this, not specificity.
app.include_router(xliff_import.router, prefix="/api/v1/xliff", tags=["XLIFF"])
app.include_router(xliff_export.router, prefix="/api/v1/xliff", tags=["XLIFF"])
# JSON provenance documents — the JSON peer of the XLIFF pair above, same
# import-before-export mounting order and the same reason.
app.include_router(json_import.router, prefix="/api/v1/json", tags=["JSON"])
app.include_router(json_export.router, prefix="/api/v1/json", tags=["JSON"])
app.include_router(redrive.router, prefix="/api/v1/redrive", tags=["Redrive"])
app.include_router(images.router, prefix="/api/v1/images", tags=["Images"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(pages.router, prefix="/api/v1/pages", tags=["Pages"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit"])
# tm (TMX import) mounted separately from xliff — a distinct legacy vendor
# format (§9b.1 of docs/graphrag-provenance-proposal.md), not another XLIFF
# route, so it gets its own prefix rather than sharing /xliff's.
app.include_router(tm.router, prefix="/api/v1/tm", tags=["Translation Memory"])
app.include_router(style.router, prefix="/api/v1/style", tags=["Style & Voice"])
app.include_router(vendors.router, prefix="/api/v1/vendors", tags=["Vendor Scorecard"])
app.include_router(consistency.router, prefix="/api/v1/consistency", tags=["Consistency"])
app.include_router(quality.router, prefix="/api/v1/quality", tags=["Automatic Quality Metrics"])
app.include_router(models.router, prefix="/api/v1/models", tags=["Model Discovery"])
app.include_router(integrations.router, prefix="/api/v1/integrations/cms", tags=["CMS Integrations"])


# The Review Shell (frontend/) is a Vite+React app now, not a static HTML
# file — it has to be built (`npm run build` in frontend/) before FastAPI can
# serve it directly. In development, run `npm run dev` in frontend/ (port
# 5173, proxies /api to this server) and frontend/demo-target/ (port 5174,
# the page the Review Shell iframes) instead of hitting this route.
FRONTEND_DIST = Path("frontend/dist")

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

# review-sdk/overlay.ts compiled to a dependency-free browser script (`npm
# run build:sdk` in frontend/) — Phase 8's fetch+rewrite loader injects this
# into pages it re-serves, which never go through Vite's dev-transform.
# Mounted at /sdk-dist, deliberately NOT /review-sdk — the Review Shell's
# own React app fetches frontend/review-sdk/*.ts as source (via Vite's dev
# transform, e.g. ReviewFrame.tsx/DocumentViewer.tsx's relative imports),
# and a same-prefix proxy/mount would shadow those legitimate requests.
REVIEW_SDK_DIST = Path("frontend/review-sdk/dist")

if REVIEW_SDK_DIST.exists():
    app.mount("/sdk-dist", StaticFiles(directory=REVIEW_SDK_DIST), name="review-sdk-dist")


@app.get("/", response_class=HTMLResponse)
async def root():
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return HTMLResponse(
        "<h1>Review Shell not built</h1>"
        "<p>Run <code>npm run build</code> in <code>frontend/</code> to serve it from here, "
        "or for development run <code>npm run dev</code> in <code>frontend/</code> (port 5173) "
        "and <code>frontend/demo-target/</code> (port 5174) alongside this server.</p>"
        '<p><a href="/docs">API docs</a></p>'
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "AI Translation Provenance System"}


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str):
    """Serves the Review Shell's index.html for client-side routes (e.g.
    /documents/{id}, the DocumentViewer's iframe target — see
    frontend/src/main.tsx's path-based routing) that aren't a real file or
    API route. Registered last: Starlette matches routes in registration
    order, so every router and the /assets mount above are tried first —
    this only catches what nothing else matched. In dev, Vite's own SPA
    fallback (port 5173) serves these paths instead; this route only matters
    once frontend/dist/ is built and served from here.

    Files Vite copies verbatim from frontend/public/ (the logo, favicon,
    etc.) land at the ROOT of frontend/dist/, not under /assets/ — only
    hashed build output goes there. Without this check, a request for e.g.
    /wordinbits-logo.png matched nothing above and fell all the way through
    to unconditionally returning index.html, so the <img> tag silently got
    an HTML document instead of image bytes. Resolved and re-checked against
    FRONTEND_DIST's own resolved path first — full_path is attacker-controlled
    input, and a naive FRONTEND_DIST / full_path join would let a "../../"
    segment escape the intended directory."""
    dist_root = FRONTEND_DIST.resolve()
    candidate = (dist_root / full_path).resolve()
    if candidate.is_relative_to(dist_root) and candidate.is_file():
        return FileResponse(candidate)
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return HTMLResponse("<h1>Review Shell not built</h1>", status_code=404)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
