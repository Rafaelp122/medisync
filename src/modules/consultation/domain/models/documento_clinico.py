"""Clinical document model issued during virtual consultation."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.core.uuid7 import uuid7
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.models.documento_item import DocumentoItem

_SHA256_HEX_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class TipoDocumentoClinico(StrEnum):
    """Permitted clinical document types issued via telemedicine (CFM 2.314/2022)."""

    RECEITA_SIMPLES = "RECEITA_SIMPLES"
    RECEITA_ANTIMICROBIANO = "RECEITA_ANTIMICROBIANO"
    RECEITA_CONTROLE_ESPECIAL_C1 = "RECEITA_CONTROLE_ESPECIAL_C1"
    ATESTADO_MEDICO = "ATESTADO_MEDICO"
    RELATORIO_ENCAMINHAMENTO = "RELATORIO_ENCAMINHAMENTO"


class DocumentoClinico(Base):
    """Entidade agregadora de documentos clínicos da telemedicina.

    Emite receitas e atestados sob ICP-Brasil e Portaria SVS/MS nº 344/98.
    Regras: Portaria 344/98, MP 2.200-2/2001 e ADR-006.
    """

    __tablename__ = "documentos_clinicos"
    __table_args__ = (
        CheckConstraint(
            "tipo_documento IN ("
            "'RECEITA_SIMPLES', "
            "'RECEITA_ANTIMICROBIANO', "
            "'RECEITA_CONTROLE_ESPECIAL_C1', "
            "'ATESTADO_MEDICO', "
            "'RELATORIO_ENCAMINHAMENTO'"
            ")",
            name="chk_documentos_tipo",
        ),
        CheckConstraint(
            "sha256_hash IS NULL OR length(sha256_hash) = 64",
            name="chk_documentos_sha256_len",
        ),
        Index("idx_documentos_atendimento", "atendimento_id"),
        Index("idx_documentos_org", "organizacao_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    atendimento_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("atendimentos.id", ondelete="RESTRICT"),
        nullable=False,
    )
    medico_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo_documento: Mapped[TipoDocumentoClinico] = mapped_column(
        String(32), nullable=False
    )
    chave_s3: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assinado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    itens: Mapped[list[DocumentoItem]] = relationship(
        "DocumentoItem",
        back_populates="documento",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __init__(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        medico_id: UUID,
        tipo_documento: TipoDocumentoClinico | str,
        chave_s3: str,
        sha256_hash: str | None = None,
        *,
        assinado_em: datetime | None = None,
        finalizado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ConsultaInvalidaError(
                f"organizacao_id inválido: {organizacao_id}; "
                "deve ser um identificador positivo (> 0)."
            )

        if not chave_s3 or not chave_s3.strip():
            raise ConsultaInvalidaError(
                f"chave_s3 inválida: {chave_s3!r}; esperado caminho não vazio."
            )

        clean_hash: str | None = None
        if sha256_hash is not None and sha256_hash.strip():
            ch = sha256_hash.strip().lower()
            if len(ch) != 64 or not _SHA256_HEX_REGEX.match(ch):
                raise ConsultaInvalidaError(
                    f"Hash SHA-256 inválido: '{sha256_hash}'. "
                    "Deve conter 64 caracteres hexadecimais (regex: ^[a-fA-F0-9]{64}$)."
                )
            clean_hash = ch

        try:
            tipo_enum = (
                tipo_documento
                if isinstance(tipo_documento, TipoDocumentoClinico)
                else TipoDocumentoClinico(str(tipo_documento).strip())
            )
        except ValueError as err:
            raise ConsultaInvalidaError(
                f"Tipo de documento clínico inválido: '{tipo_documento}'; "
                f"esperados: {[t.value for t in TipoDocumentoClinico]}."
            ) from err

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            tipo_documento=tipo_enum,
            chave_s3=chave_s3.strip(),
            sha256_hash=clean_hash,
            assinado_em=assinado_em,
            finalizado_em=finalizado_em,
        )

    @property
    def is_finalizado(self) -> bool:
        """Indica se o documento clínico foi congelado após finalização da consulta.

        Garante imutabilidade do prontuário eletrônico conforme CFM nº 1.821/2007.
        Regras: docs/explanation/domains/consultation-domain.md.
        """
        return self.finalizado_em is not None

    def marcar_finalizado(self, agora: datetime | None = None) -> None:
        """Bloqueia o documento clínico contra alterações ou exclusões posteriores.

        Assegura integridade forense sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: docs/explanation/domains/consultation-domain.md.
        """
        if self.finalizado_em is None:
            self.finalizado_em = agora or datetime.now(UTC)

    def registrar_assinatura(
        self, sha256_hash: str, assinado_em: datetime | None = None
    ) -> None:
        """Registra assinatura digital ICP-Brasil e hash (MP 2.200-2/2001).

        Regras: docs/explanation/domains/consultation-domain.md.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                f"Documento clínico '{self.id}' já finalizado; "
                "não pode receber nova assinatura."
            )
        clean_hash = sha256_hash.strip().lower()
        if len(clean_hash) != 64 or not _SHA256_HEX_REGEX.match(clean_hash):
            raise ConsultaInvalidaError(
                f"Hash SHA-256 inválido: '{sha256_hash}'. "
                "Deve conter 64 caracteres hexadecimais (regex: ^[a-fA-F0-9]{64}$)."
            )
        self.sha256_hash = clean_hash
        self.assinado_em = assinado_em or datetime.now(UTC)

    def adicionar_item(self, item: DocumentoItem) -> None:
        """Adiciona item prescrito validando substâncias restritas da Portaria 344/98.

        Bloqueia substâncias das Listas A/B e marca controle especial C1.
        Regras: Portaria 344/98 e docs/explanation/domains/consultation-domain.md.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                f"Não é permitido adicionar itens ao documento clínico '{self.id}' "
                "de consulta finalizada (is_finalizado=True)."
            )

        if item.organizacao_id != self.organizacao_id:
            raise ConsultaInvalidaError(
                "Violação de isolamento multi-tenant: organizacao_id do item "
                f"({item.organizacao_id}) difere da organizacao_id do documento "
                f"({self.organizacao_id})."
            )

        # Regra sanitária Portaria 344/98 Listas A e B
        validar_substancia_permitida_telemedicina(item.medicamento)

        if self.tipo_documento == TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1:
            item.controle_especial = True

        item.documento_id = self.id
        item.documento = self

    def validar_pode_excluir(self, status_atendimento: str | None = None) -> None:
        """Valida se a exclusão é permitida no estado atual do atendimento.

        Impede exclusão após encerramento clínico sob CFM nº 1.821/2007 e RN06.
        Regras: docs/explanation/domains/consultation-domain.md.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                f"Não é permitido excluir documento clínico '{self.id}' "
                "de consulta finalizada (is_finalizado=True)."
            )

        if status_atendimento is not None:
            status_clean = str(status_atendimento).strip().upper()
            if status_clean in _STATUS_TERMINAIS:
                raise ConsultaFinalizadaError(
                    f"Não é permitido excluir documento '{self.id}' de consulta "
                    f"finalizada (status terminal atual: '{status_clean}'; "
                    f"terminais: {sorted(_STATUS_TERMINAIS)})."
                )


@event.listens_for(DocumentoClinico, "before_delete")
def impedir_exclusao_documento_finalizado(
    _mapper: Any, _connection: Any, target: DocumentoClinico
) -> None:
    """Impede deleção física de documentos de consultas finalizadas via SQLAlchemy.

    Assegura inviolabilidade do PEP sob CFM nº 1.821/2007 e LGPD Art. 16.
    Regras: docs/explanation/domains/consultation-domain.md.
    """
    if target.is_finalizado:
        raise ConsultaFinalizadaError(
            f"Não é permitido excluir documento clínico '{target.id}' "
            "de consulta finalizada (is_finalizado=True)."
        )
