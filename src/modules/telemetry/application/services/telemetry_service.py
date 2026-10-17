"""Application service orchestrating real-time shift telemetry queries and caching."""

from src.modules.telemetry.application.dtos import PainelTelemetriaDTO
from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)
from src.modules.telemetry.application.ports.telemetry_reader_port import (
    TelemetryReaderPort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


class TelemetryService:
    """Service handling operational shift telemetry metrics with TTL caching."""

    def __init__(
        self,
        reader: TelemetryReaderPort,
        config_repo: ConfigPlantaoRepositoryPort,
        cache: TelemetryCachePort,
        cache_ttl_segundos: int = 5,
    ) -> None:
        self._reader = reader
        self._config_repo = config_repo
        self._cache = cache
        self._cache_ttl_segundos = cache_ttl_segundos

    async def obter_painel(
        self, organizacao_id: int, desconsiderar_cache: bool = False
    ) -> PainelTelemetriaDTO:
        """Fetch aggregated operational telemetry panel with caching and SLA targets."""
        if not desconsiderar_cache:
            cached = await self._cache.obter_painel(organizacao_id)
            if cached is not None:
                return cached

        config = await self._config_repo.obter_por_organizacao(organizacao_id)
        if config is None:
            config = ConfiguracaoPlantao(organizacao_id=organizacao_id)

        painel = await self._reader.obter_painel_telemetria(
            organizacao_id=organizacao_id,
            config=config,
        )

        await self._cache.salvar_painel(
            organizacao_id=organizacao_id,
            painel=painel,
            ttl_segundos=self._cache_ttl_segundos,
        )

        return painel
