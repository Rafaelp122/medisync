"""Port for reading shift attendance aggregations without importing foreign models."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from src.modules.telemetry.application.dtos import MedicoTMADTO, PainelTelemetriaDTO
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


@runtime_checkable
class TelemetryReaderPort(Protocol):
    """Protocol defining read operations for shift attendance telemetry."""

    async def obter_painel_telemetria(
        self,
        organizacao_id: int,
        config: ConfiguracaoPlantao | None = None,
        data_inicio: datetime | None = None,
    ) -> PainelTelemetriaDTO:
        """Obtain complete aggregated telemetry dashboard for the specified day."""
        ...

    async def obter_tma_por_medico(
        self,
        organizacao_id: int,
        data_inicio: datetime | None = None,
    ) -> tuple[MedicoTMADTO, ...]:
        """Obtain average attendance time aggregated per doctor."""
        ...

    async def obter_contagem_fila(
        self,
        organizacao_id: int,
    ) -> int:
        """Obtain count of patients currently waiting in queue."""
        ...

    async def obter_medicos_ativos_count(
        self,
        organizacao_id: int,
        data_inicio: datetime | None = None,
    ) -> int:
        """Obtain count of active medical doctors for the shift."""
        ...
