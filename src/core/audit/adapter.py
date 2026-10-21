"""SQLAlchemy adapter implementing AuditTrailPort (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit.models import AtorPapel, AtorTipo
from src.core.audit.ports import AuditTrailPort
from src.core.audit.service import AuditService


class SqlAuditTrailAdapter(AuditTrailPort):
    """Adaptador de auditoria delegando para AuditService na sessão corrente.

    Anexa o evento de auditoria à transação corrente sem efetuar commit prematuro.
    Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_event(
        self,
        *,
        organizacao_id: int,
        atendimento_id: UUID,
        ator_tipo: AtorTipo | str,
        ator_papel: AtorPapel | str,
        tipo_evento: str,
        ator_id: UUID | None = None,
        estado_anterior: str | None = None,
        novo_estado: str | None = None,
        tcle_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        ip_origem: str | None = None,
    ) -> UUID:
        """Anexa evento auditável append-only à transação SQLAlchemy corrente (ADR-007).

        Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
        Catálogo: docs/reference/audit/event-catalog.md
        """
        event = await AuditService.record_event(
            self._session,
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            ator_tipo=ator_tipo,
            ator_papel=ator_papel,
            tipo_evento=tipo_evento,
            ator_id=ator_id,
            estado_anterior=estado_anterior,
            novo_estado=novo_estado,
            tcle_hash=tcle_hash,
            payload=payload,
            ip_origem=ip_origem,
        )
        return event.id
