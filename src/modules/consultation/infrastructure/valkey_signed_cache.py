"""Valkey SignedCachePort with SET EX."""

from uuid import UUID

from redis.asyncio import Redis


class ValkeySignedCache:
    """Multi-worker signed-document cache backed by Valkey strings with TTL."""

    def __init__(self, valkey: Redis, key_prefix: str = "doc:assinado:") -> None:
        self._valkey = valkey
        self._prefix = key_prefix

    def _key(self, documento_id: UUID) -> str:
        return f"{self._prefix}{documento_id}"

    async def is_assinado(self, documento_id: UUID) -> bool:
        exists: object = await self._valkey.exists(self._key(documento_id))  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)

    async def marcar_assinado(
        self, documento_id: UUID, ttl_segundos: int = 86400
    ) -> None:
        await self._valkey.set(self._key(documento_id), "1", ex=max(1, ttl_segundos))  # pyright: ignore[reportUnknownMemberType]
