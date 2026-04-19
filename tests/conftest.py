"""
Pytest configuration and shared fixtures.
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import init_db


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_app():
    """Initialize app state once per test session."""
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
