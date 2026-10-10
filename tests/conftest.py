"""Global pytest fixtures and configurations for MediSync test suite."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory
from src.core.valkey import close_valkey_pool
from src.main import app

from tests.helpers import (
    auth_headers,
)
from tests.helpers import (
    clean_database_and_valkey as _clean_db_and_valkey,
)
from tests.helpers import (
    clean_database_tables as _clean_db_tables,
)

AuthedClientFactory = Callable[[str, int, UUID | None], AsyncClient]


@pytest.fixture
async def sample_async_resource() -> AsyncGenerator[str, None]:
    """Sample asynchronous resource fixture to validate pytest-asyncio loop scope."""
    await asyncio.sleep(0.001)
    yield "ready"


@pytest.fixture(autouse=True)
async def cleanup_valkey_pool_fixture() -> AsyncGenerator[None, None]:
    """Ensure Valkey connection pool is cleanly closed after each test."""
    yield
    await close_valkey_pool()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield a standard AsyncClient configured against the ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an isolated AsyncSession connected to PostgreSQL."""
    async with async_session_factory() as session:
        yield session


@pytest.fixture
def authed_client_factory() -> AuthedClientFactory:
    """Return a factory that builds an AsyncClient pre-authenticated with JWT."""

    def _build_client(
        papel: str, org_id: int, usuario_id: UUID | None = None
    ) -> AsyncClient:
        uid = usuario_id or uuid4()
        headers = {
            **auth_headers(papel=papel, org_id=org_id, usuario_id=uid),
            "X-Tenant-ID": str(org_id),
        }
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test", headers=headers)

    return _build_client


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provide a strictly typed AsyncMock of AsyncSession for fast unit tests."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
async def clean_db() -> AsyncGenerator[None, None]:
    """Ensure database tables are truncated before and after test."""
    await _clean_db_tables()
    yield
    await _clean_db_tables()


@pytest.fixture
async def clean_db_and_valkey() -> AsyncGenerator[None, None]:
    """Ensure database tables and Valkey keys are truncated."""
    await _clean_db_and_valkey()
    yield
    await _clean_db_and_valkey()
