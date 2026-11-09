"""Domain event and notification port for eligibility failure alerts (RF-05)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.modules.ambulatory.domain.enums import StatusElegibilidade


@dataclass(frozen=True)
class ElegibilidadeFalhaEvent:
    """Immutable domain event emitted when eligibility verification fails
    or times out.
    """

    atendimento_id: UUID
    organizacao_id: int
    paciente_id: UUID
    motivo: str
    status: StatusElegibilidade
    disparado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class ElegibilidadeNotifierPort(Protocol):
    """Abstract port for alerting patient waiting room on eligibility issues (RF-05)."""

    async def notificar_falha(self, evento: ElegibilidadeFalhaEvent) -> None:
        """Dispatches an alert to patient interface for payment/data regularisation."""
        ...
