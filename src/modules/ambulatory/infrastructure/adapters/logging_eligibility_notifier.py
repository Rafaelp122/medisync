"""Adapter for logging eligibility failure alerts to structured telemetry."""

import logging

from src.modules.ambulatory.application.ports.eligibility_notifier import (
    ElegibilidadeFalhaEvent,
    ElegibilidadeNotifierPort,
)

logger = logging.getLogger("medisync.ambulatory.eligibility")


class LoggingElegibilidadeNotifier(ElegibilidadeNotifierPort):
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
