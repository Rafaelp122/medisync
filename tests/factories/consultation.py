"""Typed model factories for consultation entities used across tests."""

from datetime import datetime
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
)

_DEFAULT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def make_evolucao_clinica(
    organizacao_id: int = 1,
    atendimento_id: UUID | None = None,
    medico_id: UUID | None = None,
    *,
    anamnese: str = "Paciente relata tosse seca e febre baixa há 2 dias.",
    conduta: str = "Prescrito sintomáticos, hidratação oral e isolamento.",
    exame_fisico_virtual: str | None = "Estado geral regular, sem dispneia aparente.",
    cid10_principal: str | None = "J00",
    registrado_em: datetime | None = None,
    id: UUID | None = None,
) -> EvolucaoClinica:
    """Create a typed EvolucaoClinica instance for testing."""
    return EvolucaoClinica(
        organizacao_id=organizacao_id,
        atendimento_id=atendimento_id or uuid7(),
        medico_id=medico_id or uuid7(),
        anamnese=anamnese,
        conduta=conduta,
        exame_fisico_virtual=exame_fisico_virtual,
        cid10_principal=cid10_principal,
        registrado_em=registrado_em,
        id=id or uuid7(),
    )


def make_documento_clinico(
    organizacao_id: int = 1,
    atendimento_id: UUID | None = None,
    medico_id: UUID | None = None,
    *,
    tipo_documento: TipoDocumentoClinico | str = TipoDocumentoClinico.RECEITA_SIMPLES,
    chave_s3: str = "s3://medisync-docs/1/atendimentos/default/receita.pdf",
    sha256_hash: str = _DEFAULT_SHA256,
    assinado_em: datetime | None = None,
    id: UUID | None = None,
) -> DocumentoClinico:
    """Create a typed DocumentoClinico instance for testing."""
    return DocumentoClinico(
        organizacao_id=organizacao_id,
        atendimento_id=atendimento_id or uuid7(),
        medico_id=medico_id or uuid7(),
        tipo_documento=tipo_documento,
        chave_s3=chave_s3,
        sha256_hash=sha256_hash,
        assinado_em=assinado_em,
        id=id or uuid7(),
    )


def make_documento_item(
    organizacao_id: int = 1,
    documento_id: UUID | None = None,
    *,
    medicamento: str = "Dipirona 500mg",
    dosagem: str = "1 comprimido",
    posologia: str = "Tomar 1 comprimido VO a cada 6 horas se dor ou febre.",
    duracao: str | None = "5 dias",
    controle_especial: bool = False,
    id: UUID | None = None,
) -> DocumentoItem:
    """Create a typed DocumentoItem instance for testing."""
    return DocumentoItem(
        organizacao_id=organizacao_id,
        documento_id=documento_id or uuid7(),
        medicamento=medicamento,
        dosagem=dosagem,
        posologia=posologia,
        duracao=duracao,
        controle_especial=controle_especial,
        id=id or uuid7(),
    )
