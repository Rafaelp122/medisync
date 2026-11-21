"""Application service handling shift configuration lifecycle and persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.dtos import ConfigPlantaoCommand
from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


class ConfigPlantaoService:
    """Service governing shift configuration persistence and cache invalidation."""

    def __init__(
        self,
        repo: ConfigPlantaoRepositoryPort,
        cache: TelemetryCachePort,
        session: AsyncSession,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._session = session

    async def obter_configuracao(self) -> ConfiguracaoPlantao:
        """Recupera configuração ativa do plantão ou cria padrões da plataforma.

        Garante parametrização de SLAs, TMA e limites operacionais (ADR-013).
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        config = await self._repo.obter_atual()
        if config is None:
            config = ConfiguracaoPlantao()
            await self._repo.salvar(config)
            await self._session.commit()

        return config

    async def atualizar_configuracao(
        self, command: ConfigPlantaoCommand
    ) -> ConfiguracaoPlantao:
        """Cria ou atualiza configuração do plantão, persistindo e invalidando cache.

        Valida parâmetros de alpha backpressure, TMA e ring tolerance (ADR-013).
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        config = await self._repo.obter_atual()
        if config is None:
            config = ConfiguracaoPlantao(
                medicos_ativos_planejados=command.medicos_ativos_planejados,
                alpha_backpressure=command.alpha_backpressure,
                cota_diaria_maxima=command.cota_diaria_maxima,
                tma_padrao_segundos=command.tma_padrao_segundos,
                tempo_tolerancia_ring_segundos=command.tempo_tolerancia_ring_segundos,
                modo_operacao=command.modo_operacao,
                sla_minutos_nivel_1=command.sla_minutos_nivel_1,
                sla_minutos_nivel_2=command.sla_minutos_nivel_2,
                sla_minutos_nivel_3=command.sla_minutos_nivel_3,
                sla_minutos_nivel_4=command.sla_minutos_nivel_4,
                sla_minutos_nivel_5=command.sla_minutos_nivel_5,
                atualizado_por_id=command.atualizado_por_id,
            )
            await self._repo.salvar(config)
        else:
            config.atualizar_parametros(
                medicos_ativos_planejados=command.medicos_ativos_planejados,
                alpha_backpressure=command.alpha_backpressure,
                cota_diaria_maxima=command.cota_diaria_maxima,
                tma_padrao_segundos=command.tma_padrao_segundos,
                tempo_tolerancia_ring_segundos=command.tempo_tolerancia_ring_segundos,
                modo_operacao=command.modo_operacao,
                sla_minutos_nivel_1=command.sla_minutos_nivel_1,
                sla_minutos_nivel_2=command.sla_minutos_nivel_2,
                sla_minutos_nivel_3=command.sla_minutos_nivel_3,
                sla_minutos_nivel_4=command.sla_minutos_nivel_4,
                sla_minutos_nivel_5=command.sla_minutos_nivel_5,
                atualizado_por_id=command.atualizado_por_id,
            )
            await self._repo.salvar(config)

        await self._cache.invalidar_painel()
        await self._session.commit()

        return config
