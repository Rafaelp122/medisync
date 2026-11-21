"""Pediatric or legal dependent linkage model."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7


class Dependente(Base):
    """Vínculo de dependência pediátrica ou representação legal entre pacientes.

    Regras: RN-IDE-05, RN07 (TCLE menores), LGPD Art. 11, CFM 1.821/2007.
    Documentação: docs/explanation/domains/identity-domain.md
    """

    __tablename__ = "dependentes"
    __table_args__ = (
        UniqueConstraint("titular_id", "dependente_id", name="uq_dependente_vinculo"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    titular_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dependente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    grau_parentesco: Mapped[str] = mapped_column(String(32), nullable=False)
    outorga_tcle: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        titular_id: UUID,
        dependente_id: UUID,
        grau_parentesco: str,
        outorga_tcle: bool = False,
        *,
        is_pediatrico: bool = False,
        id: UUID | None = None,
    ) -> None:
        if titular_id == dependente_id:
            raise ValidationError(
                f"Paciente não pode ser dependente de si mesmo: titular '{titular_id}' "
                f"e dependente '{dependente_id}' são idênticos."
            )

        if is_pediatrico and not outorga_tcle:
            raise ValidationError(
                f"Outorga explícita de TCLE pelo responsável legal é obrigatória para "
                f"vincular dependente pediátrico '{dependente_id}' "
                f"(recebido outorga_tcle={outorga_tcle!r}; RN-IDE-05 / RN07)."
            )

        super().__init__(
            id=id or uuid7(),
            titular_id=titular_id,
            dependente_id=dependente_id,
            grau_parentesco=grau_parentesco.strip().upper(),
            outorga_tcle=outorga_tcle,
        )
