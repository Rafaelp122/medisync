"""Port for shift configuration persistence."""

from typing import Protocol, runtime_checkable

from src.modules.telemetry.domain.models import ConfiguracaoPlantao


@runtime_checkable
class ConfigPlantaoRepositoryPort(Protocol):
    """Protocol defining persistence operations for ConfiguracaoPlantao."""

    async def obter_por_organizacao(
        self, organizacao_id: int
    ) -> ConfiguracaoPlantao | None:
        """Fetch active shift configuration for a specific organization."""
        ...

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        """Persist or update shift configuration."""
        ...
