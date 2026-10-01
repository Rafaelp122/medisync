"""Pediatric or legal dependent linkage model."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7


class Dependente(Base):
    """Pediatric or legal dependent linkage to titular patient."""

    __tablename__ = "dependentes"
    __table_args__ = (
        UniqueConstraint("titular_id", "dependente_id", name="uq_dependente_vinculo"),
        Index("idx_dependentes_org", "organizacao_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
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
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        titular_id: UUID,
        dependente_id: UUID,
        grau_parentesco: str,
        id: UUID | None = None,
    ) -> None:
        if titular_id == dependente_id:
            raise ValidationError("Paciente não pode ser dependente de si mesmo.")

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            titular_id=titular_id,
            dependente_id=dependente_id,
            grau_parentesco=grau_parentesco.strip().upper(),
        )
