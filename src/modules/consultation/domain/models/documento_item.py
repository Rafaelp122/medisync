"""Prescription document item model with explicit multi-tenant RLS isolation."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.core.uuid7 import uuid7
from src.modules.consultation.domain.exceptions import ConsultaInvalidaError
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)

if TYPE_CHECKING:
    from src.modules.consultation.domain.models.documento_clinico import (
        DocumentoClinico,
    )


class DocumentoItem(Base):
    """Prescription item entity adhering to PostgreSQL Row Level Security (RLS)."""

    __tablename__ = "documento_itens"
    __table_args__ = (
        Index("idx_documento_itens_doc", "documento_id"),
        Index("idx_documento_itens_org", "organizacao_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    documento_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documentos_clinicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    medicamento: Mapped[str] = mapped_column(String(255), nullable=False)
    dosagem: Mapped[str] = mapped_column(String(100), nullable=False)
    posologia: Mapped[str] = mapped_column(Text, nullable=False)
    duracao: Mapped[str | None] = mapped_column(String(50), nullable=True)
    controle_especial: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    documento: Mapped["DocumentoClinico | None"] = relationship(
        "DocumentoClinico",
        back_populates="itens",
    )

    def __init__(
        self,
        organizacao_id: int,
        documento_id: UUID,
        medicamento: str,
        dosagem: str,
        posologia: str,
        *,
        duracao: str | None = None,
        controle_especial: bool = False,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ConsultaInvalidaError(
                "organizacao_id inválido: deve ser um identificador positivo."
            )

        if not medicamento or not medicamento.strip():
            raise ConsultaInvalidaError(
                "Nome do medicamento é obrigatório e não pode ser vazio."
            )

        if not dosagem or not dosagem.strip():
            raise ConsultaInvalidaError(
                "Dosagem do medicamento é obrigatória e não pode ser vazia."
            )

        if not posologia or not posologia.strip():
            raise ConsultaInvalidaError(
                "Posologia do medicamento é obrigatória e não pode ser vazia."
            )

        # Regra sanitária: valida contra Listas A e B da Portaria 344/98
        validar_substancia_permitida_telemedicina(medicamento.strip())

        clean_duracao = duracao.strip() if duracao and duracao.strip() else None

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            documento_id=documento_id,
            medicamento=medicamento.strip(),
            dosagem=dosagem.strip(),
            posologia=posologia.strip(),
            duracao=clean_duracao,
            controle_especial=controle_especial,
        )
