"""Port for signed-document cache with TTL (multi-worker safe)."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class SignedCachePort(Protocol):
    """Cache contract marking clinical documents as signed with expiry."""

    async def is_assinado(self, documento_id: UUID) -> bool: ...
    async def marcar_assinado(
        self, documento_id: UUID, ttl_segundos: int = 86400
    ) -> None: ...
