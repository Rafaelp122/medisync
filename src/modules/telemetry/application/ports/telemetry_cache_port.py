"""Port for caching shift telemetry dashboard with TTL."""

from typing import Protocol, runtime_checkable

from src.modules.telemetry.application.dtos import PainelTelemetriaDTO


@runtime_checkable
class TelemetryCachePort(Protocol):
    """Protocol defining Valkey cache operations for telemetry dashboard."""

    async def obter_painel(self, organizacao_id: int) -> PainelTelemetriaDTO | None:
        """Retrieve cached telemetry dashboard if present and not expired."""
        ...

    async def salvar_painel(
        self,
        organizacao_id: int,
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        """Store telemetry dashboard into cache with specified TTL."""
        ...

    async def invalidar_painel(self, organizacao_id: int) -> None:
        """Evict cached telemetry dashboard for an organization."""
        ...
