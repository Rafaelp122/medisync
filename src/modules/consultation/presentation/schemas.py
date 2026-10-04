"""Pydantic v2 presentation schemas for consultation module."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegistrarSOAPRequest(BaseModel):
    """Payload to record or update SOAP clinical notes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    medico_id: UUID = Field(description="Identificador único do médico assistente")
    anamnese: str = Field(
        description="Subjetivo (S): Queixa, anamnese e história clínica"
    )
    conduta: str = Field(
        description="Plano (P): Conduta terapêutica, orientações e desfecho"
    )
    exame_fisico_virtual: str | None = Field(
        default=None,
        description="Objetivo (O): Exame físico por vídeo e sinais observados",
    )
    cid10_principal: str | None = Field(
        default=None,
        description="Avaliação (A): Código CID-10 principal da hipótese diagnóstica",
    )
    organizacao_id: int | None = Field(
        default=None,
        description="Identificador da organização de saúde",
    )


class EvolucaoSOAPResponse(BaseModel):
    """Response containing recorded SOAP clinical evolution notes."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    anamnese: str
    exame_fisico_virtual: str | None
    cid10_principal: str | None
    conduta: str
    registrado_em: datetime
    is_finalizado: bool


class ItemPrescricaoRequest(BaseModel):
    """Prescription medication item input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    medicamento: str = Field(
        description="Nome do princípio ativo ou medicamento comercial"
    )
    dosagem: str = Field(description="Dosagem (ex: 500mg, 10mg/ml)")
    posologia: str = Field(description="Instruções de uso (ex: 1 cp de 8 em 8 horas)")
    duracao: str | None = Field(default=None, description="Duração do tratamento")
    controle_especial: bool = Field(
        default=False,
        description="Indica se é substância da Lista C1",
    )


class ItemPrescricaoResponse(BaseModel):
    """Prescription medication item output."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None
    controle_especial: bool


class EmitirDocumentoRequest(BaseModel):
    """Payload to issue a digital clinical document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    medico_id: UUID = Field(description="Identificador único do médico")
    tipo_documento: str = Field(
        description="Tipo de documento clínico (RECEITA_SIMPLES, etc.)"
    )
    itens: list[ItemPrescricaoRequest] = Field(
        default_factory=list,
        description="Itens de medicamentos a prescrever",
    )
    chave_s3: str | None = Field(
        default=None, description="Chave de armazenamento S3/MinIO"
    )
    sha256_hash: str | None = Field(
        default=None, description="Hash SHA-256 do documento"
    )
    organizacao_id: int | None = Field(
        default=None, description="Identificador da organização"
    )


class DocumentoClinicoResponse(BaseModel):
    """Response containing issued clinical document and child items."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    atendimento_id: UUID
    organizacao_id: int
    medico_id: UUID
    tipo_documento: str
    chave_s3: str
    sha256_hash: str
    assinado_em: datetime
    is_finalizado: bool
    itens: list[ItemPrescricaoResponse]


class ProntuarioResponse(BaseModel):
    """Aggregated clinical record protected by Tier 1 and Tier 3 authorization."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    atendimento_id: UUID
    is_finalizado: bool
    evolucao: EvolucaoSOAPResponse | None = None
    documentos: list[DocumentoClinicoResponse] = Field(default_factory=list)


class AssinarDocumentoRequest(BaseModel):
    """Payload to authorize digital signature via cloud PSC."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str = Field(description="Token OAuth2 do médico emitido pelo provedor PSC")
    provider: str = Field(
        default="birdid",
        description="Provedor PSC (birdid, safeid, vidaas, fake)",
    )
    certificate_alias: str | None = Field(
        default=None,
        description="Alias ou identificador opcional do certificado no PSC",
    )


class AssinarDocumentoResponse(BaseModel):
    """Result of digital signature application."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    documento_id: UUID
    tipo_documento: str
    sha256_hash: str
    assinado_em: datetime
    tamanho_bytes: int
    status: str = "ASSINADO"


class FinalizarConsultaRequest(BaseModel):
    """Payload to conclude attendance and lock PEP records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    medico_id: UUID = Field(description="Identificador do médico assistente")
    organizacao_id: int | None = Field(
        default=None, description="Identificador da organização"
    )


class TMAStatusResponse(BaseModel):
    """Telemetry indicator for Average Consultation Time (TMA), enforcing RN06."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    atendimento_id: UUID
    tempo_decorrido_segundos: int
    tma_planejado_segundos: int
    excedeu_tma: bool
    aviso_visual: str


class ValidarPrescricaoRequest(BaseModel):
    """Payload to pre-validate a medication against controlled substances lists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    medicamento: str = Field(description="Nome do medicamento a validar")


# --- LiveKit WebRTC Schemas ---


class LiveKitTokenRequest(BaseModel):
    """Payload to request an authenticated LiveKit room access token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organizacao_id: UUID = Field(
        description="Identificador único da organização de saúde"
    )
    participant_id: UUID = Field(
        description="Identificador único do usuário (médico ou paciente)"
    )
    role: Literal["medico", "paciente"] = Field(
        description="Papel clínico do participante"
    )
    participant_name: str | None = Field(
        default=None,
        description="Nome de exibição opcional para a sala WebRTC",
    )
    is_publisher: bool = Field(
        default=True,
        description="Habilita publicação de trilhas de áudio/vídeo",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Tempo de vida útil do token em segundos",
    )


class LiveKitTokenResponse(BaseModel):
    """Response containing signed JWT token and connection metadata."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    token: str = Field(description="JWT assinado com Video Grants do LiveKit")
    room_name: str = Field(description="Nome canônico da sala org_{org}_atend_{atend}")
    participant_identity: str = Field(
        description="Identidade particionada (medico_{id} ou paciente_{id})"
    )
    server_url: str = Field(description="URL canônica do servidor SFU LiveKit")
    expires_in: int = Field(description="Validade em segundos")


# --- Document Validation & Portal Schemas ---


class ItemValidacaoResponse(BaseModel):
    """Prescribed drug item summary for public verification."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None = None
    controle_especial: bool = False


class ValidarDocumentoResponse(BaseModel):
    """Public verification details with masked patient data (LGPD compliant)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

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
    itens: list[ItemValidacaoResponse]
