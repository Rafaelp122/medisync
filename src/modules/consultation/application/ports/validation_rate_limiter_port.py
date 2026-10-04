"""Port for public validation sliding-window rate limiting (Valkey pattern)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ValidationRateLimitResult:
    """Result of a public validation rate limit check."""

    permitido: bool
    tentativas_restantes: int
    retry_after_segundos: int


@runtime_checkable
class ValidationRateLimiterPort(Protocol):
    """Sliding-window rate limiter for public document validation endpoints."""

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 30,
        janela_segundos: int = 60,
    ) -> ValidationRateLimitResult:
        """Check attempt count against threshold and increment atomically."""
        ...

    async def resetar(self, chave: str) -> None:
        """Reset counters for the given key."""
        ...
