"""Port and DTO specifications for clinical document PDF generation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.consultation.domain.models.documento_clinico import (
    TipoDocumentoClinico,
)


@dataclass(frozen=True)
class DocumentoItemPDFDTO:
    """Item representation for rendered prescription PDF."""

    medicamento: str
    dosagem: str
    posologia: str
    duracao: str | None = None
    controle_especial: bool = False


@dataclass(frozen=True)
class DocumentoPDFPayload:
    """Full data payload required to generate compliant clinical PDF/A documents."""

    documento_id: UUID
    tipo_documento: TipoDocumentoClinico | str
    data_emissao: datetime
    organizacao_nome: str
    medico_nome: str
    medico_crm: str
    medico_crm_uf: str
    paciente_nome: str
    paciente_cpf: str
    organizacao_cnpj: str | None = None
    organizacao_cnes: str | None = None
    organizacao_endereco: str | None = None
    organizacao_telefone: str | None = None
    medico_rqe: str | None = None
    paciente_data_nascimento: str | None = None
    paciente_endereco: str | None = None
    itens: list[DocumentoItemPDFDTO] = field(default_factory=list)
    texto_livre: str | None = None
    dias_afastamento: int | None = None
    cid10: str | None = None
    cid10_autorizado_paciente: bool = True
    especialidade_encaminhamento: str | None = None
    motivo_encaminhamento: str | None = None
    validation_url: str | None = None
    sha256_hash: str | None = None


@runtime_checkable
class PDFGeneratorPort(Protocol):
    """Port interface for PDF/A clinical document compilation."""

    def gerar_pdf(self, payload: DocumentoPDFPayload) -> bytes:
        """Compile a compliant PDF/A document with ITI verification QR code.

        Args:
            payload: Clinical document data and metadata.

        Returns:
            Raw PDF bytes matching PDF/A archiving standard.
        """
        ...
