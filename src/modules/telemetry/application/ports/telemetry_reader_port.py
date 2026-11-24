"""Port for reading shift attendance aggregations without importing foreign models."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from src.modules.telemetry.application.dtos import PainelTelemetriaDTO
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


@runtime_checkable
class TelemetryReaderPort(Protocol):
    """Protocol defining read operation for shift attendance telemetry."""

    async def obter_painel_telemetria(
        self,
        config: ConfiguracaoPlantao | None = None,
        data_inicio: datetime | None = None,
    ) -> PainelTelemetriaDTO:
        """Obtain complete aggregated telemetry dashboard for the specified day."""
        ...
