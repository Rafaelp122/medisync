"""Data Transfer Objects for SUS ambulatory production and eligibility.

Conforme RF-02 e ADR-012.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.ambulatory.domain.enums import StatusElegibilidade


@dataclass(frozen=True)
class RequisicaoElegibilidade:
    """Payload de entrada imutável para validação de elegibilidade e cadastro SUS."""

    organizacao_id: int
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


@dataclass(frozen=True)
class BpaProducaoDTO:
    """DTO representativo de item de produção ambulatorial individualizada (BPA-I)."""

    atendimento_id: UUID
    cnes: str
    codigo_sigtap: str
    carater_atendimento: str
    consolidado_em: datetime


@dataclass(frozen=True)
class BpaArquivoExportadoDTO:
    """DTO com o conteúdo magnético SIA-SUS e metadados de exportação."""

    conteudo: str
    nome_arquivo: str
    total_registros: int
    total_folhas: int
    competencia: str


@dataclass(frozen=True)
class ListaProducaoAmbulatorialDTO:
    """DTO paginado de listagem da produção ambulatorial por competência."""

    items: list[BpaProducaoDTO]
    total: int
    competencia: str
    organizacao_id: int
    page: int
    size: int


@dataclass(frozen=True)
class BpaRegistroDetalheDTO:
    """DTO com visão desnormalizada para composição do detalhe tipo 03 do BPA-I."""

    producao_id: UUID
    atendimento_id: UUID
    profissional_id: UUID
    paciente_id: UUID
    cnes: str
    codigo_sigtap: str
    carater_atendimento: str
    competencia: str
    consolidado_em: datetime
    paciente_nome: str
    paciente_cns: str
    paciente_cpf: str | None
    paciente_data_nascimento: str  # AAAAMMDD
    paciente_sexo: str  # M ou F
    paciente_ibge: str
    medico_cns: str
    medico_cbo: str
    org_nome: str
    org_sigla: str
    org_cnpj: str
    cid: str = ""
    idade: int = 0
