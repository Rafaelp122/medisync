"""In-memory SignedCachePort for tests."""

import time
from uuid import UUID


class MemorySignedCache:
    """Ephemeral TTL cache keyed by document UUID."""

    def __init__(self) -> None:
        self._store: dict[UUID, float] = {}

    async def is_assinado(self, documento_id: UUID) -> bool:
        exp = self._store.get(documento_id)
        if exp is None:
            return False
        if time.time() > exp:
            del self._store[documento_id]
            return False
        return True

    async def marcar_assinado(
        self, documento_id: UUID, ttl_segundos: int = 86400
    ) -> None:
        self._store[documento_id] = time.time() + max(1, ttl_segundos)
