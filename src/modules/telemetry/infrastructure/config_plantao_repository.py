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

    async def obter_atual(self) -> ConfiguracaoPlantao | None:
        """Fetch singleton shift configuration of the platform."""
        stmt = select(ConfiguracaoPlantao).where(
            ConfiguracaoPlantao.singleton_guard.is_(True)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def salvar(self, configuracao: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
        """Persist or update shift configuration."""
        self._session.add(configuracao)
        await self._session.flush()
        return configuracao
