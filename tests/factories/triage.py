"""Typed model factories for triage entities used across tests."""

from datetime import datetime
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.triage.domain.models import Triagem


def make_triagem(
    organizacao_id: int = 1,
    atendimento_id: UUID | None = None,
    *,
    queixa_principal: str = "Febre alta e calafrios",
    prioridade_calculada: int = 3,
    sintomas_alerta: list[str] | None = None,
    alerta_samu_disparado: bool = False,
    avaliado_em: datetime | None = None,
    id: UUID | None = None,
) -> Triagem:
    """Create a typed Triagem instance for unit and integration testing."""
    return Triagem(
        organizacao_id=organizacao_id,
        atendimento_id=atendimento_id or uuid7(),
        queixa_principal=queixa_principal,
        prioridade_calculada=prioridade_calculada,
        sintomas_alerta=sintomas_alerta,
        alerta_samu_disparado=alerta_samu_disparado,
        avaliado_em=avaliado_em,
        id=id or uuid7(),
    )
