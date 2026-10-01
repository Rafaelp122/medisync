"""Typed model factories for queue entities used across tests."""

from datetime import datetime
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)


def make_atendimento(
    organizacao_id: int = 1,
    paciente_id: UUID | None = None,
    *,
    medico_id: UUID | None = None,
    status: StatusAtendimento | str = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
    prioridade_clinica: int | PrioridadeClinica = PrioridadeClinica.NAO_URGENTE,
    tcle_hash: str | None = None,
    data_entrada_fila: datetime | None = None,
    chamada_iniciada_em: datetime | None = None,
    chamada_finalizada_em: datetime | None = None,
    id: UUID | None = None,
) -> Atendimento:
    """Create a typed Atendimento instance for unit and integration testing."""
    return Atendimento(
        organizacao_id=organizacao_id,
        paciente_id=paciente_id or uuid7(),
        medico_id=medico_id,
        status=status,
        prioridade_clinica=prioridade_clinica,
        tcle_hash=tcle_hash,
        data_entrada_fila=data_entrada_fila,
        chamada_iniciada_em=chamada_iniciada_em,
        chamada_finalizada_em=chamada_finalizada_em,
        id=id or uuid7(),
    )
