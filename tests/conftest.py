"""Global pytest fixtures and configurations."""

import asyncio
from collections.abc import AsyncGenerator

import pytest


@pytest.fixture
async def sample_async_resource() -> AsyncGenerator[str, None]:
    """Sample asynchronous resource fixture to validate pytest-asyncio loop scope."""
    await asyncio.sleep(0.001)
    yield "ready"
