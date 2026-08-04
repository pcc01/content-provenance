# ── AI Translation Provenance System — Dockerfile ─────────────────────────────
#
# Multi-stage: a Node stage builds the Review Shell + review-sdk bundles
# (frontend/dist/, frontend/review-sdk/dist/) that app/main.py serves via
# StaticFiles, so `docker build` is self-contained on any host — no manual
# `npm run build` step to remember before building the image (previously
# required, easy to forget on a remote deploy host with no local dev
# workflow reminding you).

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
# Builds frontend/dist/ (Review Shell) + review-sdk/dist/ (overlay.js,
# harvest.js) in one pass — see frontend/package.json's "build" script.
RUN npm run build

FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so startup is fast
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" || true

# Chromium + its system deps for Phase 8's fetch+rewrite page review
# (playwright the pip package is already in requirements.txt — this installs
# the actual browser binary and OS libraries it needs to run headless)
RUN playwright install --with-deps chromium

# Copy application code
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Built frontend assets from the Node stage — overwrites the source-only
# frontend/ copy above with the same tree plus dist/ output.
COPY --from=frontend-build /frontend/dist ./frontend/dist
COPY --from=frontend-build /frontend/review-sdk/dist ./frontend/review-sdk/dist

# Expose port
EXPOSE 8000

# Apply migrations, then start the server. (app/core/database.py also has a
# create_all dev-fallback for when Alembic hasn't been run, but a container
# should always run migrations properly rather than rely on that.)
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
