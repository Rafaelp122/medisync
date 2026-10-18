"""Application service handling shift configuration lifecycle and persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.dtos import (
    ConfigPlantaoCommand,
    ConfigPlantaoResultDTO,
)
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

    async def obter_configuracao(self, organizacao_id: int) -> ConfigPlantaoResultDTO:
        """Recupera configuração ativa do plantão ou cria padrões do tenant.

        Garante parametrização de SLAs, TMA e limites operacionais.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        config = await self._repo.obter_por_organizacao(organizacao_id)
        if config is None:
            config = ConfiguracaoPlantao(organizacao_id=organizacao_id)
            await self._repo.salvar(config)
            await self._session.commit()

        return ConfigPlantaoResultDTO.from_entity(config)

    async def atualizar_configuracao(
        self, command: ConfigPlantaoCommand
    ) -> ConfigPlantaoResultDTO:
        """Cria ou atualiza configuração do plantão, persistindo e invalidando cache.

        Valida parâmetros de alpha backpressure, TMA e ring tolerance do domínio.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        config = await self._repo.obter_por_organizacao(command.organizacao_id)
        if config is None:
            config = ConfiguracaoPlantao(
                organizacao_id=command.organizacao_id,
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

        await self._cache.invalidar_painel(command.organizacao_id)
        await self._session.commit()

        return ConfigPlantaoResultDTO.from_entity(config)
