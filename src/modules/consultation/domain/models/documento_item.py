"""Prescription document item model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
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
    """Prescription item entity linked to DocumentoClinico."""

    __tablename__ = "documento_itens"
    __table_args__ = (Index("idx_documento_itens_doc", "documento_id"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
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
        lazy="raise",
    )

    def __init__(
        self,
        documento_id: UUID,
        medicamento: str,
        dosagem: str,
        posologia: str,
        *,
        duracao: str | None = None,
        controle_especial: bool = False,
        id: UUID | None = None,
    ) -> None:
        if not medicamento or not medicamento.strip():
            raise ConsultaInvalidaError(
                f"Nome do medicamento é obrigatório e não pode ser vazio: "
                f"{medicamento!r}."
            )

        if not dosagem or not dosagem.strip():
            raise ConsultaInvalidaError(
                f"Dosagem do medicamento é obrigatória e não pode ser vazia: "
                f"{dosagem!r}."
            )

        if not posologia or not posologia.strip():
            raise ConsultaInvalidaError(
                f"Posologia do medicamento é obrigatória e não pode ser vazia: "
                f"{posologia!r}."
            )

        # Regra sanitária: valida contra Listas A e B da Portaria 344/98
        validar_substancia_permitida_telemedicina(medicamento.strip())

        clean_duracao = duracao.strip() if duracao and duracao.strip() else None

        super().__init__(
            id=id or uuid7(),
            documento_id=documento_id,
            medicamento=medicamento.strip(),
            dosagem=dosagem.strip(),
            posologia=posologia.strip(),
            duracao=clean_duracao,
            controle_especial=controle_especial,
        )
