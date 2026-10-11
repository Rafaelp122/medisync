"""Distributed token revocation checker and writer backed by Valkey/Redis."""

import contextlib
from uuid import UUID

from redis.asyncio import ConnectionPool, Redis

from src.core.valkey import get_valkey_pool


def _format_revoked_key(token_id: str | UUID) -> str:
    return f"auth:revoked:{token_id}"


async def is_token_revoked(
    token_id: str | UUID,
    pool: ConnectionPool | None = None,
) -> bool:
    """Check if token identifier (JTI) is marked as revoked in Valkey."""
    try:
        active_pool = pool if pool is not None else get_valkey_pool()
        client = Redis(connection_pool=active_pool)
        key = _format_revoked_key(token_id)
        exists = await client.exists(key)  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)
    except Exception:
        # Fallback to False when cache is unreachable or during unit tests
        return False


async def revoke_token_id(
    token_id: str | UUID,
    ttl_seconds: int = 86400 * 7,
    pool: ConnectionPool | None = None,
) -> None:
    """Mark token identifier (JTI) as revoked in Valkey until TTL expires."""
    with contextlib.suppress(Exception):
        active_pool = pool if pool is not None else get_valkey_pool()
        client = Redis(connection_pool=active_pool)
        key = _format_revoked_key(token_id)
        ttl = max(1, ttl_seconds)
        await client.set(key, "1", ex=ttl)  # pyright: ignore[reportUnknownMemberType]
