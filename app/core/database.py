"""
Database layer — PostgreSQL-backed (async SQLAlchemy).

Public interface (init_db / get_db) is unchanged from the earlier in-memory
version so callers (`from app.core.database import get_db`) don't need to
change their imports; get_db() now returns a PostgresRepository
(app/core/db/repository.py) whose methods are async — every call site needs
`await`, but nothing needs to change *what* it imports or calls.
"""

from typing import Optional

from sqlalchemy import text

from app.core.db.models import Base
from app.core.db.repository import PostgresRepository
from app.core.db.session import async_session_factory, engine

_repo: Optional[PostgresRepository] = None


async def init_db():
    global _repo
    async with engine.begin() as conn:
        # Phase 13's embedding columns need this before create_all compiles
        # them — cheap/idempotent, and Alembic's own 0014 migration runs the
        # same statement for the real migration path.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Dev convenience: ensures the schema exists even before `alembic
        # upgrade head` has been run. create_all is checkfirst=True by
        # default, so this is a no-op (not a conflict) once Alembic owns
        # the schema — Alembic remains the source of truth for migrations.
        await conn.run_sync(Base.metadata.create_all)

    _repo = PostgresRepository(async_session_factory)

    # Seed default agents (idempotent — get_or_create_agent dedups by name+type).
    await _repo.get_or_create_agent(
        name="claude-3-7-sonnet",
        agent_type="SoftwareAgent",
        model_version="claude-3-7-sonnet-20250219",
        organization="Anthropic",
        metadata={"capabilities": ["translation", "summarization"]},
    )
    await _repo.get_or_create_agent(
        name="System",
        agent_type="SoftwareAgent",
        organization="AI Provenance System",
        metadata={"role": "orchestration"},
    )
    print("✓ Database initialized (PostgreSQL)")


def get_db() -> PostgresRepository:
    if _repo is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _repo
