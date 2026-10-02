"""Queue overflow and regulatory transition notifier port (RN05)."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

logger = logging.getLogger("medisync.queue.overflow")


@dataclass(frozen=True)
class QueueOverflowEvent:
    """Immutable event payload emitted when admission threshold is breached (RN05)."""

    organizacao_id: int
    motivo: str
    pacientes_aguardando: int
    medicos_ativos: int
    tempo_restante_segundos: float
    carga_estimada_segundos: float
    mensagem_orientacao: str
    evento: str = "QUEUE_OVERFLOW_TRANSIT"
    alpha_utilizado: float = 1.25
    disparado_em: datetime = field(default_factory=lambda: datetime.now(UTC))


class QueueOverflowNotifierPort(Protocol):
    """Abstract port for asynchronous dispatch of queue overflow events."""

    async def emitir_transbordo(self, event: QueueOverflowEvent) -> None:
        """Dispatches the QUEUE_OVERFLOW_TRANSIT event for regulatory integration."""
        ...


class LoggingQueueOverflowNotifier:
    """Default fallback implementation logging overflow events to stdout/telemetry."""

    async def emitir_transbordo(self, event: QueueOverflowEvent) -> None:
        """Logs the QUEUE_OVERFLOW_TRANSIT event with structured context."""
        logger.warning(
            "Event %s emitted for org=%d: reason=%s, waiting=%d, doctors=%d, "
            "load=%.1fs, remaining=%.1fs, alpha=%.2f",
            event.evento,
            event.organizacao_id,
            event.motivo,
            event.pacientes_aguardando,
            event.medicos_ativos,
            event.carga_estimada_segundos,
            event.tempo_restante_segundos,
            event.alpha_utilizado,
        )
