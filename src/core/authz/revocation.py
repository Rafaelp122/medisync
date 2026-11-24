"""Distributed fail-closed token revocation port and Valkey/memory adapters."""

import contextlib
from functools import lru_cache
from typing import Annotated, Protocol, runtime_checkable

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from src.core.config import get_settings
from src.core.errors import ServiceUnavailableError
from src.core.valkey import get_valkey_pool


@runtime_checkable
class TokenRevocationPort(Protocol):
    """Protocol for checking and registering revoked JWT token identifiers (JTI)."""

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        """Mark token JTI as revoked until expiry."""
        ...

    async def marcar_revogado_se_nao_revogado(
        self, jti: str, exp_segundos: int = 86400 * 7
    ) -> bool:
        """Atomically revoke token JTI if absent (False if already revoked)."""
        ...

    async def is_revogado(self, jti: str) -> bool:
        """Check whether token JTI was revoked."""
        ...


def _format_revoked_key(jti: str) -> str:
    return f"auth:revoked:{jti}"


async def _close_owned_client(client: Redis | None, owns_client: bool) -> None:
    if owns_client and client is not None:
        with contextlib.suppress(Exception):
            await client.aclose()


class ValkeyTokenRevocation(TokenRevocationPort):
    """Fail-closed distributed token revocation store backed by Valkey/Redis."""

    def __init__(
        self,
        valkey: Redis | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        self._valkey = valkey
        self._pool = pool

    def _acquire_client(self) -> tuple[Redis, bool]:
        if self._valkey is not None:
            return self._valkey, False
        active_pool = self._pool if self._pool is not None else get_valkey_pool()
        return Redis(connection_pool=active_pool), True

    async def _set_revocation_flag(
        self,
        jti: str,
        exp_segundos: int,
        *,
        nx: bool,
    ) -> bool:
        client: Redis | None = None
        owns_client = False
        try:
            client, owns_client = self._acquire_client()
            key = _format_revoked_key(jti)
            ttl = max(1, exp_segundos)
            result = await client.set(key, "1", ex=ttl, nx=nx)  # pyright: ignore[reportUnknownMemberType]
            return bool(result)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            err_type = type(exc).__name__
            raise ServiceUnavailableError(
                "Serviço de revogação de tokens (Valkey) indisponível ao registrar "
                f"revogação de '{jti}' ({err_type}: {exc})."
            ) from exc
        finally:
            await _close_owned_client(client, owns_client)

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        """Persist token JTI revocation in Valkey; aborts with 503 on infra failure."""
        await self._set_revocation_flag(jti, exp_segundos, nx=False)

    async def marcar_revogado_se_nao_revogado(
        self, jti: str, exp_segundos: int = 86400 * 7
    ) -> bool:
        """Atomically mark token JTI revoked via Valkey SET NX; aborts 503 on error."""
        return await self._set_revocation_flag(jti, exp_segundos, nx=True)

    async def is_revogado(self, jti: str) -> bool:
        """Check if token JTI is revoked in Valkey (strictly fail-closed on errors)."""
        client: Redis | None = None
        owns_client = False
        try:
            client, owns_client = self._acquire_client()
            key = _format_revoked_key(jti)
            exists = await client.exists(key)  # pyright: ignore[reportUnknownMemberType]
            return bool(exists)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            err_type = type(exc).__name__
            raise ServiceUnavailableError(
                "Serviço de revogação de tokens (Valkey) indisponível ao verificar "
                f"token '{jti}' ({err_type}: {exc})."
            ) from exc
        finally:
            await _close_owned_client(client, owns_client)


class MemoryTokenRevocation(TokenRevocationPort):
    """In-memory token revocation store for deterministic tests without Docker."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        """Mark token JTI as revoked in memory."""
        self._revoked.add(jti)

    async def marcar_revogado_se_nao_revogado(
        self, jti: str, exp_segundos: int = 86400 * 7
    ) -> bool:
        """Atomically mark token JTI revoked in memory if not already present."""
        if jti in self._revoked:
            return False
        self._revoked.add(jti)
        return True

    async def is_revogado(self, jti: str) -> bool:
        """Return True if token JTI was revoked in memory."""
        return jti in self._revoked

    def clear(self) -> None:
        """Reset revoked identifiers stored in memory."""
        self._revoked.clear()


@lru_cache(maxsize=1)
def _get_memory_token_revocation() -> MemoryTokenRevocation:
    return MemoryTokenRevocation()


def get_token_revocation() -> TokenRevocationPort:
    """Resolve active TokenRevocationPort adapter from TOKEN_REVOCATION_BACKEND."""
    settings = get_settings()
    if settings.TOKEN_REVOCATION_BACKEND == "memory":  # noqa: S105
        return _get_memory_token_revocation()
    return ValkeyTokenRevocation()


TokenRevocationDep = Annotated[TokenRevocationPort, Depends(get_token_revocation)]
