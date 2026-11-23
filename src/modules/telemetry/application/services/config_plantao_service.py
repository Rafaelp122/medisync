"""Application service handling shift configuration lifecycle and persistence."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.dtos import ConfigPlantaoInput
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
        """Recupera configuração ativa do plantão ou provisiona padrão atomicamente.

        Garante parametrização de SLAs, TMA e limites operacionais (ADR-013).
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        existente = await self._repo.obter_atual()
        if existente is not None:
            return existente

        config = await self._repo.obter_ou_criar_padrao()
        await self._session.commit()
        return config

    async def atualizar_configuracao(
        self,
        dados: ConfigPlantaoInput,
        *,
        atualizado_por_id: UUID | None = None,
    ) -> ConfiguracaoPlantao:
        """Cria ou atualiza configuração do plantão, persistindo e invalidando cache.

        Valida parâmetros de alpha backpressure, TMA e ring tolerance (ADR-013).
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        # Valida invariantes antes de provisionar ou mutar a linha singleton
        _ = ConfiguracaoPlantao(
            medicos_ativos_planejados=dados.medicos_ativos_planejados,
            alpha_backpressure=dados.alpha_backpressure,
            cota_diaria_maxima=dados.cota_diaria_maxima,
            tma_padrao_segundos=dados.tma_padrao_segundos,
            tempo_tolerancia_ring_segundos=dados.tempo_tolerancia_ring_segundos,
            modo_operacao=dados.modo_operacao,
            sla_minutos_nivel_1=dados.sla_minutos_nivel_1,
            sla_minutos_nivel_2=dados.sla_minutos_nivel_2,
            sla_minutos_nivel_3=dados.sla_minutos_nivel_3,
            sla_minutos_nivel_4=dados.sla_minutos_nivel_4,
            sla_minutos_nivel_5=dados.sla_minutos_nivel_5,
            atualizado_por_id=atualizado_por_id,
        )

        config = await self._repo.obter_ou_criar_padrao()
        config.atualizar_parametros(
            medicos_ativos_planejados=dados.medicos_ativos_planejados,
            alpha_backpressure=dados.alpha_backpressure,
            cota_diaria_maxima=dados.cota_diaria_maxima,
            tma_padrao_segundos=dados.tma_padrao_segundos,
            tempo_tolerancia_ring_segundos=dados.tempo_tolerancia_ring_segundos,
            modo_operacao=dados.modo_operacao,
            sla_minutos_nivel_1=dados.sla_minutos_nivel_1,
            sla_minutos_nivel_2=dados.sla_minutos_nivel_2,
            sla_minutos_nivel_3=dados.sla_minutos_nivel_3,
            sla_minutos_nivel_4=dados.sla_minutos_nivel_4,
            sla_minutos_nivel_5=dados.sla_minutos_nivel_5,
            atualizado_por_id=atualizado_por_id,
        )
        await self._repo.salvar(config)
        await self._cache.invalidar_painel()
        await self._session.commit()

        return config
