"""Port for shift configuration persistence."""

from typing import Protocol, runtime_checkable

from src.modules.telemetry.domain.models import ConfiguracaoPlantao


@runtime_checkable
class ConfigPlantaoRepositoryPort(Protocol):
    """Protocol defining persistence operations for singleton ConfiguracaoPlantao."""

    async def obter_atual(self) -> ConfiguracaoPlantao | None:
        """Fetch active singleton shift configuration of the platform."""
        ...

    async def obter_ou_criar_padrao(self) -> ConfiguracaoPlantao:
        """Fetch singleton shift configuration or atomically provision default row."""
        ...

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        """Persist or update shift configuration."""
        ...
