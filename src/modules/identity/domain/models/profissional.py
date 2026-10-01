"""Clinical professional and administrative staff entity."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from src.modules.identity.domain.models._helpers import clean_digits

PapelProfissional = Literal["ADMIN_GLOBAL", "GESTOR_UNIDADE", "MEDICO", "FATURAMENTO"]


class Profissional(Base):
    """Clinical staff, unit managers, and administrative users."""

    __tablename__ = "profissionais"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "email", name="uq_profissional_org_email"),
        UniqueConstraint("organizacao_id", "cpf", name="uq_profissional_org_cpf"),
        Index("idx_profissionais_org_papel", "organizacao_id", "papel"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    cpf: Mapped[str] = mapped_column(String(14), nullable=False)
    nome_completo: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False)
    crm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crm_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        cpf: str,
        nome_completo: str,
        email: str,
        senha_hash: str,
        papel: str,
        crm: str | None = None,
        crm_uf: str | None = None,
        ativo: bool = True,
        id: UUID | None = None,
    ) -> None:
        digits = clean_digits(cpf)
        if len(digits) != 11:
            raise ValidationError(
                "CPF do profissional inválido: deve conter 11 dígitos numéricos."
            )

        if papel == "MEDICO" and (not crm or not crm_uf):
            raise ValidationError(
                "CRM e UF são obrigatórios para profissionais com papel "
                "MEDICO (CFM 2.314/2022)."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            cpf=digits,
            nome_completo=nome_completo,
            email=email.strip().lower(),
            senha_hash=senha_hash,
            papel=papel,
            crm=crm.strip() if crm else None,
            crm_uf=crm_uf.strip().upper() if crm_uf else None,
            ativo=ativo,
        )

    def alterar_senha_hash(self, novo_hash: str) -> None:
        """Update password hash without coupling to hashing implementation."""
        self.senha_hash = novo_hash

    def is_medico(self) -> bool:
        return self.papel == "MEDICO"

    def ativar(self) -> None:
        self.ativo = True

    def desativar(self) -> None:
        self.ativo = False
