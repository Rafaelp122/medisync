"""SQLAlchemy 2.0 async repository for ConfiguracaoPlantao."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


class SqlConfigPlantaoRepository(ConfigPlantaoRepositoryPort):
    """Repository handling persistence of shift configurations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_atual(self) -> ConfiguracaoPlantao | None:
        """Fetch singleton shift configuration of the platform."""
        stmt = select(ConfiguracaoPlantao).where(
            ConfiguracaoPlantao.singleton_guard.is_(True)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def obter_ou_criar_padrao(self) -> ConfiguracaoPlantao:
        """Fetch singleton shift config or atomically provision default row."""
        existente = await self.obter_atual()
        if existente is not None:
            return existente

        padrao = ConfiguracaoPlantao()
        stmt = (
            pg_insert(ConfiguracaoPlantao)
            .values(
                id=padrao.id,
                singleton_guard=True,
                medicos_ativos_planejados=padrao.medicos_ativos_planejados,
                alpha_backpressure=padrao.alpha_backpressure,
                cota_diaria_maxima=padrao.cota_diaria_maxima,
                tma_padrao_segundos=padrao.tma_padrao_segundos,
                tempo_tolerancia_ring_segundos=padrao.tempo_tolerancia_ring_segundos,
                modo_operacao=padrao.modo_operacao,
                sla_minutos_nivel_1=padrao.sla_minutos_nivel_1,
                sla_minutos_nivel_2=padrao.sla_minutos_nivel_2,
                sla_minutos_nivel_3=padrao.sla_minutos_nivel_3,
                sla_minutos_nivel_4=padrao.sla_minutos_nivel_4,
                sla_minutos_nivel_5=padrao.sla_minutos_nivel_5,
                criado_em=padrao.criado_em,
                atualizado_em=padrao.atualizado_em,
                atualizado_por_id=padrao.atualizado_por_id,
            )
            .on_conflict_do_nothing(index_elements=["singleton_guard"])
        )
        await self._session.execute(stmt)
        config = await self.obter_atual()
        if config is None:
            raise RuntimeError(
                "ConfiguracaoPlantao singleton ausente após INSERT ON CONFLICT "
                f"(id_tentativa='{padrao.id}')."
            )
        return config

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        """Persist or update shift configuration."""
        self._session.add(configuracao)
        await self._session.flush()
        return configuracao
