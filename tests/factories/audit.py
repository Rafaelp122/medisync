"""Typed model factory for AuditEvent entity used across tests."""

from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent
from src.core.uuid7 import uuid7


def make_audit_event(
    organizacao_id: int = 1,
    atendimento_id: UUID | None = None,
    *,
    ator_tipo: AtorTipo | str = AtorTipo.PROFISSIONAL,
    ator_papel: AtorPapel | str = AtorPapel.MEDICO,
    tipo_evento: str = "STATUS_ATENDIMENTO_ATUALIZADO",
    ator_id: UUID | None = None,
    estado_anterior: str | None = "APTO_PARA_CHAMADA",
    novo_estado: str | None = "CHAMANDO_PACIENTE",
    tcle_hash: str | None = None,
    payload: dict[str, Any] | None = None,
    ip_origem: str | None = "127.0.0.1",
    registrado_em: datetime | None = None,
    id: UUID | None = None,
) -> AuditEvent:
    """Create a typed AuditEvent instance for testing."""
    final_ator_id = ator_id
    if final_ator_id is None and str(ator_tipo).upper() in (
        "PROFISSIONAL",
        "PACIENTE",
    ):
        final_ator_id = uuid7()

    return AuditEvent(
        organizacao_id=organizacao_id,
        atendimento_id=atendimento_id or uuid7(),
        ator_tipo=ator_tipo,
        ator_papel=ator_papel,
        tipo_evento=tipo_evento,
        ator_id=final_ator_id,
        estado_anterior=estado_anterior,
        novo_estado=novo_estado,
        tcle_hash=tcle_hash,
        payload=payload if payload is not None else {},
        ip_origem=ip_origem,
        registrado_em=registrado_em,
        id=id or uuid7(),
    )
