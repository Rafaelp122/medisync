"""SQLAlchemy 2.0 async repository for ConfiguracaoPlantao."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


class SqlConfigPlantaoRepository(ConfigPlantaoRepositoryPort):
    """Repository handling persistence of shift configurations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_por_organizacao(
        self, organizacao_id: int
    ) -> ConfiguracaoPlantao | None:
        """Fetch active shift configuration for a specific organization."""
        stmt = select(ConfiguracaoPlantao).where(
            ConfiguracaoPlantao.organizacao_id == organizacao_id
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        """Persist or update shift configuration."""
        self._session.add(configuracao)
        await self._session.flush()
        return configuracao
