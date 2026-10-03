"""Worker execution context utilities and shared connection accessors."""

import contextlib
from collections.abc import AsyncGenerator
from typing import Any, cast

from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import Settings, get_settings
from src.core.database import async_session_factory, engine
from src.core.valkey import get_valkey_pool


def get_settings_from_ctx(ctx: dict[str, Any]) -> Settings:
    """Extract cached Settings instance from worker context or fallback."""
    extracted = ctx.get("settings")
    if extracted is not None:
        return cast("Settings", extracted)
    return get_settings()


def get_db_engine_from_ctx(ctx: dict[str, Any]) -> AsyncEngine:
    """Extract shared database AsyncEngine from context or fallback to singleton."""
    extracted = ctx.get("db_engine")
    if extracted is not None:
        return cast("AsyncEngine", extracted)
    return engine


def get_session_factory_from_ctx(
    ctx: dict[str, Any],
) -> async_sessionmaker[AsyncSession]:
    """Extract async_sessionmaker from worker context or fallback to singleton."""
    extracted = ctx.get("db_session_factory")
    if extracted is not None:
        return cast("async_sessionmaker[AsyncSession]", extracted)
    return async_session_factory


@contextlib.asynccontextmanager
async def get_db_session_from_ctx(
    ctx: dict[str, Any],
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager providing an isolated database session from worker context."""
    factory = get_session_factory_from_ctx(ctx)
    async with factory() as session:
        yield session


def get_valkey_from_ctx(ctx: dict[str, Any]) -> Redis:
    """Retrieve asynchronous Redis/Valkey client reusing context connection pool."""
    client = ctx.get("valkey_client")
    if client is not None:
        return cast("Redis", client)
    pool = ctx.get("valkey_pool")
    if pool is not None:
        return Redis(connection_pool=cast("ConnectionPool", pool))
    return Redis(connection_pool=get_valkey_pool())
