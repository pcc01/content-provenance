"""
Pytest configuration and shared fixtures.

Requires a reachable PostgreSQL instance (see docker-compose.yml — `docker-compose
up -d postgres`, or point DATABASE_URL/POSTGRES_* env vars at your own). The
schema is dropped and recreated once per test session so runs are deterministic
regardless of what a previous run (or manual poking via the API) left behind.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import init_db
from app.core.db.models import Base
from app.core.db.session import engine

# No custom `event_loop` fixture here — pytest-asyncio >=0.23 ignores/deprecates
# that override in favor of `asyncio_default_fixture_loop_scope = "session"`
# (see pyproject.toml). That setting is what actually matters: the async
# SQLAlchemy engine below is a module-level singleton, and its connection
# pool is bound to whichever event loop first uses it — if pytest-asyncio
# handed different tests different (function-scoped) loops, later tests would
# try to reuse pooled asyncpg connections on a closed loop and blow up with
# "Event loop is closed" / "got result for unknown protocol state" errors.
# Session-scoped loops keep everything on one loop for the whole run.


@pytest.fixture(scope="session", autouse=True)
async def setup_app():
    """Reset the schema and initialize app state once per test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await init_db()
    yield


@pytest.fixture
async def client():
    """Async HTTP client pointed at the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
