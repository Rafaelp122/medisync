"""Worker execution context utilities and shared connection accessors."""

import contextlib
from collections.abc import AsyncGenerator
from typing import Any, cast

from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import get_session_factory
from src.core.valkey import get_valkey_pool


def get_session_factory_from_ctx(
    ctx: dict[str, Any],
) -> async_sessionmaker[AsyncSession]:
    """Extract async_sessionmaker from worker context or fallback to singleton."""
    extracted = ctx.get("db_session_factory")
    if extracted is not None:
        return cast("async_sessionmaker[AsyncSession]", extracted)
    return get_session_factory()


@contextlib.asynccontextmanager
async def get_db_session_from_ctx(
    ctx: dict[str, Any],
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager providing an isolated database session from worker context."""
    factory = get_session_factory_from_ctx(ctx)
    async with factory() as session:
        yield session


@contextlib.asynccontextmanager
async def get_valkey_from_ctx(
    ctx: dict[str, Any],
) -> AsyncGenerator[Redis, None]:
    """Yield Valkey client from ctx or pool, closing pool-owned clients on exit."""
    client = ctx.get("valkey_client")
    if client is not None:
        yield cast("Redis", client)
        return

    pool = ctx.get("valkey_pool")
    target_pool = (
        cast("ConnectionPool", pool) if pool is not None else get_valkey_pool()
    )
    owned_client = Redis(connection_pool=target_pool)
    try:
        yield owned_client
    finally:
        await owned_client.aclose()
