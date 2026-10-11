"""Valkey distributed token revocation adapter and in-memory test fake."""

from redis.asyncio import Redis

from src.core.valkey import get_valkey_pool
from src.modules.auth.application.ports.token_revocation_port import TokenRevocationPort


class ValkeyTokenRevocation(TokenRevocationPort):
    """Distributed token revocation store backed by Valkey/Redis keys."""

    def __init__(self, valkey: Redis | None = None) -> None:
        self._valkey = (
            valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
        )

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        key = f"auth:revoked:{jti}"
        ttl = max(1, exp_segundos)
        await self._valkey.set(key, "1", ex=ttl)  # pyright: ignore[reportUnknownMemberType]

    async def is_revogado(self, jti: str) -> bool:
        key = f"auth:revoked:{jti}"
        exists = await self._valkey.exists(key)  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)


class MemoryTokenRevocation(TokenRevocationPort):
    """In-memory token revocation store for fast unit testing."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        self._revoked.add(jti)

    async def is_revogado(self, jti: str) -> bool:
        return jti in self._revoked
