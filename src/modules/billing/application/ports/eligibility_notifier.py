"""Domain event and notification port for eligibility failure alerts (RF-05)."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.modules.billing.domain.enums import StatusElegibilidade

logger = logging.getLogger("medisync.billing.eligibility")


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


class LoggingElegibilidadeNotifier:
    """Default fallback logging eligibility alerts to structured telemetry."""

    async def notificar_falha(self, evento: ElegibilidadeFalhaEvent) -> None:
        """Logs structured warning for eligibility failure."""
        logger.warning(
            "Event ELEGIBILIDADE_FALHA: org=%d, atendimento=%s, paciente=%s, "
            "status=%s, motivo=%s",
            evento.organizacao_id,
            evento.atendimento_id,
            evento.paciente_id,
            evento.status.value,
            evento.motivo,
            extra={
                "organizacao_id": evento.organizacao_id,
                "atendimento_id": str(evento.atendimento_id),
                "paciente_id": str(evento.paciente_id),
                "status": evento.status.value,
                "motivo": evento.motivo,
            },
        )
