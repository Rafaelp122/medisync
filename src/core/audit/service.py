"""Synchronous transactional audit logging service (ADR-007)."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent
from src.core.uuid7 import uuid7


class AuditService:
    """Service dispatching append-only audit trail entries within active transaction."""

    @staticmethod
    async def record_event(
        session: AsyncSession,
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
        id: UUID | None = None,
    ) -> AuditEvent:
        """Create and add an AuditEvent to the session within current transaction."""
        event = AuditEvent(
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
            id=id or uuid7(),
        )
        session.add(event)
        return event

    @staticmethod
    async def list_events_by_atendimento(
        session: AsyncSession,
        atendimento_id: UUID,
    ) -> Sequence[AuditEvent]:
        """Retrieve full chronological audit trail for a clinical attendance."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.atendimento_id == atendimento_id)
            .order_by(AuditEvent.registrado_em.asc())
        )
        res = await session.execute(stmt)
        return res.scalars().all()
