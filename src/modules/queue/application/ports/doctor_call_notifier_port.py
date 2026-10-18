"""Doctor call notification port (ADR-001)."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class DoctorCallNotifierPort(Protocol):
    """Porta abstrata para notificação em tempo real de chamada médica iniciada."""

    async def notificar_chamada_iniciada(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int,
        chamada_iniciada_em: str,
    ) -> None:
        """Dispara evento realtime para o canal do médico."""
        ...
