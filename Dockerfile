# ── AI Translation Provenance System — Dockerfile ─────────────────────────────
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

# Copy application code
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Expose port
EXPOSE 8000

# Apply migrations, then start the server. (app/core/database.py also has a
# create_all dev-fallback for when Alembic hasn't been run, but a container
# should always run migrations properly rather than rely on that.)
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
