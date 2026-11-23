"""Data Transfer Objects for SUS ambulatory production and eligibility.

Conforme RF-02 e ADR-012.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.ambulatory.domain.bpa_formatter import (
    BpaArquivoExportadoDTO,
    BpaPendenciaCadastral,
    BpaRegistroDetalheDTO,
)
from src.modules.ambulatory.domain.enums import StatusElegibilidade

__all__ = [
    "BpaArquivoExportadoDTO",
    "BpaPendenciaCadastral",
    "BpaRegistroDetalheDTO",
    "ConsolidarTeleconsultaCommand",
    "RequisicaoElegibilidade",
    "ResultadoElegibilidade",
]


@dataclass(frozen=True)
class RequisicaoElegibilidade:
    """Payload de entrada imutável para validação de elegibilidade e cadastro SUS."""

    atendimento_id: UUID
    paciente_id: UUID
    cpf: str | None = None
    cns: str | None = None


@dataclass(frozen=True)
class ResultadoElegibilidade:
    """Resultado imutável da avaliação de elegibilidade SUS."""

    aprovado: bool
    status: StatusElegibilidade
    motivo: str | None = None
    codigo_autorizacao: str | None = None
    expira_em: datetime | None = None


@dataclass(frozen=True)
class ConsolidarTeleconsultaCommand:
    """Comando de aplicação para consolidação de produção ambulatorial SUS (BPA-I)."""

    atendimento_id: UUID
    profissional_id: UUID
    paciente_id: UUID
    cnes: str
    codigo_sigtap: str = "03.01.01.025-0"
    carater_atendimento: str = "02"
    paciente_cns: str | None = None
    paciente_cpf: str | None = None
    paciente_data_nascimento: str | None = None
