"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe env var parsing.
"""

import os
from typing import List


class Settings:
    """
    Reads configuration from environment variables with sensible defaults.
    In production, set these via .env file or your container orchestration platform.
    """

    # ── Application ───────────────────────────────────────────────────────────
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_reload: bool = os.getenv("APP_RELOAD", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "info")

    # ── Translation Backend ───────────────────────────────────────────────────
    translation_provider: str = os.getenv("TRANSLATION_PROVIDER", "mock")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    deepl_api_key: str = os.getenv("DEEPL_API_KEY", "")

    # ── Haystack ──────────────────────────────────────────────────────────────
    haystack_document_store: str = os.getenv("HAYSTACK_DOCUMENT_STORE", "memory")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    elasticsearch_host: str = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))

    # ── Database ──────────────────────────────────────────────────────────────
    database_backend: str = os.getenv("DATABASE_BACKEND", "postgres")
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('POSTGRES_USER','provenance_user')}"
        f":{os.getenv('POSTGRES_PASSWORD','changeme')}"
        f"@{os.getenv('POSTGRES_HOST','localhost')}"
        f":{os.getenv('POSTGRES_PORT','5432')}"
        f"/{os.getenv('POSTGRES_DB','provenance')}",
    )

    # ── Quality Scoring / Redrive ────────────────────────────────────────────
    scoring_provider: str = os.getenv("SCORING_PROVIDER", "claude")  # claude | ollama
    redrive_provider: str = os.getenv("REDRIVE_PROVIDER", "")  # blank = reuse TRANSLATION_PROVIDER
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_qe_model: str = os.getenv(
        "OLLAMA_QE_MODEL", "hf.co/s3nh/Unbabel-TowerInstruct-7B-v0.1-GGUF:Q4_K_M"
    )
    quality_threshold_default: float = float(os.getenv("QUALITY_THRESHOLD_DEFAULT", "80"))

    # ── Image Assets ──────────────────────────────────────────────────────────
    image_storage_dir: str = os.getenv("IMAGE_STORAGE_DIR", "data/images")

    # ── XLIFF ─────────────────────────────────────────────────────────────────
    xliff_version: str = os.getenv("XLIFF_VERSION", "2.0")
    xliff_tool_name: str = os.getenv("XLIFF_TOOL_NAME", "AI Translation Provenance System")
    xliff_tool_version: str = os.getenv("XLIFF_TOOL_VERSION", "1.0.0")

    # ── CORS ──────────────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> List[str]:
        raw = os.getenv("CORS_ORIGINS", "*")
        return [o.strip() for o in raw.split(",")]

    # ── Security ──────────────────────────────────────────────────────────────
    api_key_required: bool = os.getenv("API_KEY_REQUIRED", "false").lower() == "true"
    api_key: str = os.getenv("API_KEY", "")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


# Singleton
settings = Settings()
