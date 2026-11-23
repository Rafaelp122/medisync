"""Typed model factories for triage entities used across tests."""

from datetime import datetime
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.triage.domain.models import Triagem


def make_triagem(
    atendimento_id: UUID | None = None,
    *,
    queixa_principal: str = "Febre alta e calafrios",
    prioridade_calculada: int | None = None,
    escala_dor: int = 0,
    sintomas_alerta: list[str] | None = None,
    alerta_samu_disparado: bool = False,
    avaliado_em: datetime | None = None,
    id: UUID | None = None,
) -> Triagem:
    """Create a typed Triagem instance for unit and integration testing."""
    clean_sintomas = sintomas_alerta if sintomas_alerta is not None else ["febre"]
    target_atend_id = atendimento_id or uuid7()
    target_id = id or uuid7()
    if prioridade_calculada is None:
        return Triagem.criar_avaliada(
            atendimento_id=target_atend_id,
            queixa_principal=queixa_principal,
            sintomas=clean_sintomas,
            escala_dor=escala_dor,
            alerta_samu_disparado=alerta_samu_disparado,
            avaliado_em=avaliado_em,
            id=target_id,
        )
    return Triagem(
        atendimento_id=target_atend_id,
        queixa_principal=queixa_principal,
        prioridade_calculada=prioridade_calculada,
        escala_dor=escala_dor,
        sintomas_alerta=clean_sintomas,
        alerta_samu_disparado=alerta_samu_disparado,
        avaliado_em=avaliado_em,
        id=target_id,
    )
