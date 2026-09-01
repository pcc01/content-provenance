"""
Application configuration loaded from environment variables.

Every field below reads os.getenv at class-definition time, so a local .env
has to be loaded into the process environment *before* this module's body
runs. load_dotenv() here does that for every entry point (uvicorn, pytest,
one-off scripts) — previously only docker-compose injected .env, so
`make run` / bare `uvicorn` silently fell back to the built-in defaults
(notably POSTGRES_PORT=5432, which collides with an unrelated local stack).
"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Resolved relative to the repo root (app/core/config.py -> parents[2]) so it
# works regardless of the process CWD. No-op if the file is absent, and it
# never overrides a variable already set in the environment — so real
# container/production env vars and `uvicorn --env-file` still take
# precedence over a stray .env on disk.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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
    # Phase 16 — the DEFAULT provider (used when a request doesn't pick one
    # explicitly); every provider below is also selectable per-request via
    # TranslateRequest.provider / RedriveRunRequest.redrive_provider /
    # scoring_provider — see app/core/translation_backends.py's
    # get_translation_backend() and app/core/scoring/factory.py's get_scorer().
    translation_provider: str = os.getenv("TRANSLATION_PROVIDER", "mock")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    deepl_api_key: str = os.getenv("DEEPL_API_KEY", "")

    # OpenAI (translate + evaluate) — also the client shape LMStudio/vLLM
    # reuse (app/core/llm_clients.py's OpenAICompatibleClient).
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Google Gemini (translate + evaluate) — distinct from Google
    # Translate below, which is NMT-only, no evaluate capability.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # Microsoft Translator (Azure Cognitive Services) — NMT, translate only.
    ms_translator_key: str = os.getenv("MS_TRANSLATOR_KEY", "")
    ms_translator_region: str = os.getenv("MS_TRANSLATOR_REGION", "")
    ms_translator_endpoint: str = os.getenv("MS_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")

    # LMStudio — local OpenAI-compatible server, no real API key needed.
    lmstudio_url: str = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")
    lmstudio_model: str = os.getenv("LMSTUDIO_MODEL", "local-model")

    # vLLM — local OpenAI-compatible server, no real API key needed.
    vllm_url: str = os.getenv("VLLM_URL", "http://localhost:8000/v1")
    vllm_model: str = os.getenv("VLLM_MODEL", "local-model")

    # Ollama as a TRANSLATION backend (it was already used for evaluation —
    # see ollama_qe_model below — but never for translation). Defaults to
    # Tower-Plus-9B, not the older TowerInstruct-7B-v0.1 this project's
    # evaluation path originally shipped with — Tower+ is the current
    # (2025) generation, CC-BY-NC-SA-4.0, 5.76GB at Q4_K_M, competitive
    # WMT24++ translation numbers. Tower models are multi-task (translate
    # AND evaluate in one model) — see docs/quality-evaluation-research.md
    # §10, which also confirmed this exact GGUF repo/quant exists.
    ollama_translation_model: str = os.getenv(
        "OLLAMA_TRANSLATION_MODEL", "hf.co/mradermacher/Tower-Plus-9B-GGUF:Q4_K_M"
    )

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
    scoring_provider: str = os.getenv("SCORING_PROVIDER", "claude")  # claude | ollama | mprometheus | openai | gemini | lmstudio | vllm
    redrive_provider: str = os.getenv("REDRIVE_PROVIDER", "")  # blank = reuse TRANSLATION_PROVIDER
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # M-Prometheus (Unbabel) as an LLM-judge scoring provider — a scalar
    # 1-5 MT-quality judge run locally via Ollama GGUF, on its own
    # absolute-grading rubric (NOT the shared MQM-JSON contract). Default
    # is the 14B imatrix Q4_K_M (~9GB, fits a 12GB card for short QE
    # prompts); drop to M-Prometheus-7B-GGUF:Q5_K_M (~5.5GB) if it contends
    # for VRAM with the translation/embedding models. Runs through
    # ollama_url above. See app/core/scoring/mprometheus_scorer.py.
    mprometheus_model: str = os.getenv(
        "MPROMETHEUS_MODEL", "hf.co/mradermacher/M-Prometheus-14B-i1-GGUF:i1-Q4_K_M"
    )
    # auto | reference_free | prefer_reference — how the judge sources a
    # "Score 5" reference (near-exact TM hit / none). See the scorer module.
    mprometheus_reference_mode: str = os.getenv("MPROMETHEUS_REFERENCE_MODE", "auto")
    # Phase 16 — upgraded from the original TowerInstruct-7B-v0.1 to
    # Tower-Plus-9B (see ollama_translation_model above for why) and moved
    # ollama_scorer.py from a hand-rolled prompt string to Ollama's
    # /api/chat endpoint, which applies whichever chat template is
    # embedded in the GGUF itself — sidesteps a real templating bug this
    # project had (prompting Mistral-style `[INST]...[/INST]` tags against
    # a model documented to expect ChatML), found during
    # docs/quality-evaluation-research.md §10's research.
    ollama_qe_model: str = os.getenv(
        "OLLAMA_QE_MODEL", "hf.co/mradermacher/Tower-Plus-9B-GGUF:Q4_K_M"
    )
    quality_threshold_default: float = float(os.getenv("QUALITY_THRESHOLD_DEFAULT", "80"))

    # ── Phase 13: pgGraph + Tone/Style/Voice Provenance ──────────────────────
    style_scoring_provider: str = os.getenv("STYLE_SCORING_PROVIDER", "claude")  # only "claude" for now
    style_threshold_default: float = float(os.getenv("STYLE_THRESHOLD_DEFAULT", "70"))
    # Retrieval is on by default — the whole point of Phase 13 is grounding
    # AI translation in style/glossary context rather than scoring blind
    # after the fact. Off switch exists for environments with no style
    # guides configured yet, where a retrieval attempt is pure overhead.
    graph_retrieval_enabled: bool = os.getenv("GRAPH_RETRIEVAL_ENABLED", "true").lower() == "true"
    graph_retrieval_top_k: int = int(os.getenv("GRAPH_RETRIEVAL_TOP_K", "5"))

    # ── Image Assets ──────────────────────────────────────────────────────────
    image_storage_dir: str = os.getenv("IMAGE_STORAGE_DIR", "data/images")

    # ── Documents (Phase 7 — original bytes kept for round-trip export) ──────
    document_storage_dir: str = os.getenv("DOCUMENT_STORAGE_DIR", "data/documents")
    # Optional path to the Tesseract binary for in-image OCR (pytesseract);
    # blank = rely on it being on PATH. See app/core/documents/ocr.py.
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")

    # ── XLIFF ─────────────────────────────────────────────────────────────────
    xliff_version: str = os.getenv("XLIFF_VERSION", "2.0")
    xliff_tool_name: str = os.getenv("XLIFF_TOOL_NAME", "AI Translation Provenance System")
    xliff_tool_version: str = os.getenv("XLIFF_TOOL_VERSION", "1.0.0")

    # ── CMS Integration (app/core/integrations/) ─────────────────────────────
    # Which provider is active — see app/core/integrations/factory.py.
    # "strapi" is the only one implemented today; "directus"/"payload" are
    # accepted values that fail loudly with what's missing, not silently.
    cms_provider: str = os.getenv("CMS_PROVIDER", "strapi")
    # Field name written on the CMS entry alongside the translated field,
    # holding the full ProvenanceRecord (see app/core/cms_service.py).
    cms_provenance_field: str = os.getenv("CMS_PROVENANCE_FIELD", "content_provenance")
    # Strapi — same per-provider env var naming as the translation
    # providers above (DEEPL_API_KEY, OPENAI_API_KEY, ...); future
    # DIRECTUS_*/PAYLOAD_* vars will follow the same pattern once built.
    strapi_base_url: str = os.getenv("STRAPI_BASE_URL", "")
    strapi_api_token: str = os.getenv("STRAPI_API_TOKEN", "")
    strapi_timeout_seconds: float = float(os.getenv("STRAPI_TIMEOUT_SECONDS", "15"))

    # ── TMS Integration (app/core/integrations/, app/core/tms_service.py) ─────
    # A TMS manages the translation/review workflow (Crowdin, Phrase,
    # Lokalise, ...) — distinct from a CMS, which publishes content. Only
    # "crowdin" is implemented; others fail loudly via get_tms_integration().
    tms_provider: str = os.getenv("TMS_PROVIDER", "crowdin")
    # crowdin.com: https://api.crowdin.com/api/v2 ; Crowdin Enterprise:
    # https://{organization}.api.crowdin.com/api/v2
    crowdin_base_url: str = os.getenv("CROWDIN_BASE_URL", "https://api.crowdin.com/api/v2")
    crowdin_project_id: str = os.getenv("CROWDIN_PROJECT_ID", "")
    crowdin_api_token: str = os.getenv("CROWDIN_API_TOKEN", "")
    # String-based Crowdin projects attach strings to a branch. Blank = use
    # the project's first branch (usually "main"); set a name to target /
    # create a specific one.
    crowdin_branch: str = os.getenv("CROWDIN_BRANCH", "")
    # Shared secret appended as ?secret=… to the webhook callback URL and
    # verified (hmac.compare_digest) on every inbound POST /integrations/tms/webhook.
    crowdin_webhook_secret: str = os.getenv("CROWDIN_WEBHOOK_SECRET", "")
    crowdin_timeout_seconds: float = float(os.getenv("CROWDIN_TIMEOUT_SECONDS", "20"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> List[str]:
        raw = os.getenv("CORS_ORIGINS", "*")
        return [o.strip() for o in raw.split(",")]

    # ── Security ──────────────────────────────────────────────────────────────
    api_key_required: bool = os.getenv("API_KEY_REQUIRED", "false").lower() == "true"
    api_key: str = os.getenv("API_KEY", "")

    # ── Email Notifications (audit lead alerts) ─────────────────────────────────
    # Fires an email to notify_email_to whenever a customer runs a site audit
    # (see app/core/notifications.py + app/api/audit.py). Off by default so a
    # deployment without SMTP creds doesn't error — it just skips silently.
    email_notifications_enabled: bool = (
        os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() == "true"
    )
    notify_email_to: str = os.getenv("NOTIFY_EMAIL_TO", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    # Optional — if set, the notification email links straight to the
    # audit's PDF report (e.g. https://audit.thewordinbits.com).
    public_app_url: str = os.getenv("PUBLIC_APP_URL", "")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


# Singleton
settings = Settings()
