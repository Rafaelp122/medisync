"""Application port for append-only audit trail emission (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from src.core.audit.models import AtorPapel, AtorTipo


@runtime_checkable
class AuditTrailPort(Protocol):
    """Porta abstrata para persistência atômica de eventos de auditoria append-only.

    Garante conformidade médico-legal (CFM 2.314/2022) e LGPD Art. 11.
    Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
    """

    async def record_event(
        self,
        *,
        organizacao_id: int,
        ator_tipo: AtorTipo | str,
        ator_papel: AtorPapel | str,
        tipo_evento: str,
        atendimento_id: UUID | None = None,
        ator_id: UUID | None = None,
        estado_anterior: str | None = None,
        novo_estado: str | None = None,
        tcle_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        ip_origem: str | None = None,
    ) -> UUID:
        """Registra evento na transação corrente sem realizar commit prematuro."""
        ...
