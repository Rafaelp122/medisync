"""Domain event and notification port for patient no-show during call ring (RN02)."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

logger = logging.getLogger("medisync.queue.no_show")


@dataclass(frozen=True)
class PacienteAusenteEvent:
    """Immutable domain event emitted when a patient does not answer in 45s."""

    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    paciente_id: UUID
    tempo_toque_segundos: int = 45
    evento: str = "PACIENTE_AUSENTE"
    disparado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class PacienteAusenteNotifierPort(Protocol):
    """Abstract port for dispatching patient absent / no-show domain events."""

    async def emitir_paciente_ausente(self, event: PacienteAusenteEvent) -> None:
        """Dispatches the PACIENTE_AUSENTE event to subscribers or telemetry."""
        ...


class LoggingPacienteAusenteNotifier:
    """Default fallback logging no-show events to structured telemetry."""

    async def emitir_paciente_ausente(self, event: PacienteAusenteEvent) -> None:
        """Logs the PACIENTE_AUSENTE event with contextual diagnostics."""
        logger.warning(
            "Event %s: org=%d, atendimento=%s, medico=%s, paciente=%s, ring=%ds",
            event.evento,
            event.organizacao_id,
            event.atendimento_id,
            event.medico_id,
            event.paciente_id,
            event.tempo_toque_segundos,
        )
