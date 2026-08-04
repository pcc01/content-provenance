"""Async SQLAlchemy engine/session factory, built from settings.database_url
(already assembled from POSTGRES_* env vars in app/core/config.py)."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _asyncpg_url(url: str) -> str:
    """settings.database_url is a plain postgresql:// DSN (also usable by
    sync tools like Alembic/psql) — the app itself needs the asyncpg driver
    variant."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine: AsyncEngine = create_async_engine(
    _asyncpg_url(settings.database_url), pool_pre_ping=True, future=True
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
