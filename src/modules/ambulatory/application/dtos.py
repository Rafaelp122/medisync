"""Data Transfer Objects for health insurance and SUS eligibility (RF-02)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.billing.domain.enums import StatusElegibilidade


@dataclass(frozen=True)
class RequisicaoElegibilidade:
    """Immutable input payload requesting insurance or SUS eligibility check."""

    organizacao_id: int
    atendimento_id: UUID
    paciente_id: UUID
    cpf: str | None = None
    cns: str | None = None
    operadora_id: str | None = None
    numero_carteirinha: str | None = None


@dataclass(frozen=True)
class ResultadoElegibilidade:
    """Immutable result from eligibility provider evaluation."""

    aprovado: bool
    status: StatusElegibilidade
    motivo: str | None = None
    codigo_autorizacao: str | None = None
    expira_em: datetime | None = None
