"""Data Transfer Objects for the consultation module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        EvolucaoClinica,
    )


@dataclass(frozen=True)
class LiveKitTokenRequestDTO:
    """Request DTO to generate a LiveKit room access token."""

    atendimento_id: UUID
    organizacao_id: int
    participant_id: UUID
    role: Literal["medico", "paciente"]
    participant_name: str | None = None
    is_publisher: bool = True
    ttl_seconds: int = 3600


@dataclass(frozen=True)
class LiveKitTokenResponseDTO:
    """Response DTO containing LiveKit access token and connection metadata."""

    token: str
    room_name: str
    participant_identity: str
    server_url: str
    expires_in: int


@dataclass(frozen=True)
class RegistrarEvolucaoSOAPCommand:
    """Command to record or update medical SOAP clinical notes."""

    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    anamnese: str  # Subjetivo (S)
    conduta: str  # Plano (P)
    exame_fisico_virtual: str | None = None  # Objetivo (O)
    cid10_principal: str | None = None  # Avaliação (A)


@dataclass(frozen=True)
class CriarItemPrescricaoDTO:
    """Individual medication item within a digital prescription."""

    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None = None
    controle_especial: bool = False


@dataclass(frozen=True)
class EmitirDocumentoClinicoCommand:
    """Command to issue an electronic clinical document with prescription items."""

    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    tipo_documento: str
    itens: list[CriarItemPrescricaoDTO] = field(default_factory=list)
    chave_s3: str = ""
    sha256_hash: str = ""


@dataclass(frozen=True)
class FinalizarConsultaCommand:
    """Command to lock attendance records, marking consultation concluded."""

    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID


@dataclass(frozen=True)
class TMAStatusDTO:
    """Telemetry indicator for Average Consultation Time (TMA), enforcing RN06."""

    atendimento_id: UUID
    tempo_decorrido_segundos: int
    tma_planejado_segundos: int
    excedeu_tma: bool
    aviso_visual: str


@dataclass(frozen=True)
class ProntuarioResumoDTO:
    """Aggregated clinical record view for an attendance."""

    atendimento_id: UUID
    evolucao: "EvolucaoClinica | None"
    documentos: "list[DocumentoClinico]"
    is_finalizado: bool


@dataclass(frozen=True)
class ItemValidacaoDTO:
    """Prescribed drug item snapshot for public verification."""

    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None = None
    controle_especial: bool = False


@dataclass(frozen=True)
class DocumentoValidacaoResult:
    """Service result for public document authenticity verification."""

    documento_id: UUID
    tipo_documento: str
    status_documento: str
    sha256_hash: str
    assinado_em: datetime | None
    emissor_medico_nome: str
    emissor_medico_crm: str
    emissor_medico_uf: str
    organizacao_nome: str
    paciente_nome_mascarado: str
    paciente_cpf_mascarado: str
    assinatura_digital_valida: bool
    conformidade_icp_brasil: bool
    itens: list[ItemValidacaoDTO]


@dataclass(frozen=True)
class DownloadResult:
    """Service result for presigned download URL generation."""

    documento_id: UUID
    download_url: str
    expires_in_seconds: int
    chave_s3: str


@dataclass(frozen=True)
class DocumentoAssinadoResult:
    """Service result for ICP-Brasil PAdES signing (ADR-008 output DTO)."""

    documento_id: UUID
    tipo_documento: str
    sha256_hash: str
    assinado_em: datetime
    tamanho_bytes: int
    status: str = "ASSINADO"
