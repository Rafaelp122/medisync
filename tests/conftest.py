"""Global pytest fixtures and configurations."""

import asyncio
from collections.abc import AsyncGenerator

import pytest


@pytest.fixture
async def sample_async_resource() -> AsyncGenerator[str, None]:
    """Sample asynchronous resource fixture to validate pytest-asyncio loop scope."""
    await asyncio.sleep(0.001)
    yield "ready"


@pytest.fixture(autouse=True)
async def cleanup_valkey_pool_fixture() -> AsyncGenerator[None]:
    """Ensure Valkey connection pool is cleanly closed after each test."""
    yield
    from src.core.valkey import close_valkey_pool

    await close_valkey_pool()
