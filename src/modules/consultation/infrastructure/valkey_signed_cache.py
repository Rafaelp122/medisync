"""Valkey SignedCachePort with SET EX."""

from uuid import UUID

from redis.asyncio import Redis

from src.core.valkey import get_valkey_pool


class ValkeySignedCache:
    """Multi-worker signed-document cache backed by Valkey strings with TTL.

    Proveniência Diátaxis:
    - Chaves e TTLs: docs/reference/valkey/keys-dictionary.md
    - ICP-Brasil: docs/user-stories/US-10-prescricao-assinatura-icp-brasil.md
    """

    def __init__(
        self,
        valkey: Redis | None = None,
        key_prefix: str = "doc:assinado:",
    ) -> None:
        self._valkey = valkey
        self._prefix = key_prefix

    def _get_valkey(self) -> Redis:
        if self._valkey is not None:
            return self._valkey
        return Redis(connection_pool=get_valkey_pool())

    def _key(self, documento_id: UUID) -> str:
        return f"{self._prefix}{documento_id}"

    async def is_assinado(self, documento_id: UUID) -> bool:
        client = self._get_valkey()
        exists: object = await client.exists(self._key(documento_id))  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)

    async def marcar_assinado(
        self, documento_id: UUID, ttl_segundos: int = 86400
    ) -> None:
        client = self._get_valkey()
        await client.set(self._key(documento_id), "1", ex=max(1, ttl_segundos))  # pyright: ignore[reportUnknownMemberType]
