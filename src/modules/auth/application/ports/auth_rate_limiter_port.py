"""Port interface for anti-brute force and credential stuffing rate limiting."""

from typing import Protocol, runtime_checkable

from src.modules.auth.application.dtos import RateLimitResultDTO


@runtime_checkable
class AuthRateLimiterPort(Protocol):
    """Port for sliding window rate limiting on authentication attempts."""

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 5,
        janela_segundos: int = 900,
    ) -> RateLimitResultDTO:
        """Check current attempt count against threshold and increment atomically."""
        ...

    async def resetar(self, chave: str) -> None:
        """Reset attempt counters for the given key upon successful login."""
        ...
