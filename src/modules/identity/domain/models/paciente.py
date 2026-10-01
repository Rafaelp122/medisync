"""Patient model supporting adult and pediatric two-phase onboarding."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.identity.domain.models._helpers import clean_digits


class Paciente(Base):
    """Patient model supporting adult and pediatric two-phase onboarding."""

    __tablename__ = "pacientes"
    __table_args__ = (
        CheckConstraint(
            "cpf IS NOT NULL OR cns IS NOT NULL",
            name="chk_documento_paciente_obrigatorio",
        ),
        Index(
            "uq_paciente_org_cpf",
            "organizacao_id",
            "cpf",
            unique=True,
            postgresql_where=text("cpf IS NOT NULL"),
        ),
        Index(
            "uq_paciente_org_cns",
            "organizacao_id",
            "cns",
            unique=True,
            postgresql_where=text("cns IS NOT NULL"),
        ),
        Index("idx_pacientes_org_telefone", "organizacao_id", "telefone"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    cns: Mapped[str | None] = mapped_column(String(15), nullable=True)
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=False)
    nome_completo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_mae: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sexo_biologico: Mapped[str | None] = mapped_column(String(1), nullable=True)
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    alergias: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        data_nascimento: date,
        telefone: str,
        cpf: str | None = None,
        cns: str | None = None,
        nome_completo: str | None = None,
        nome_mae: str | None = None,
        sexo_biologico: str | None = None,
        cep: str | None = None,
        logradouro: str | None = None,
        numero: str | None = None,
        bairro: str | None = None,
        cidade: str | None = None,
        estado: str | None = None,
        alergias: list[str] | None = None,
        id: UUID | None = None,
    ) -> None:
        clean_cpf = clean_digits(cpf) if cpf else None
        clean_cns = clean_digits(cns) if cns else None

        if not clean_cpf and not clean_cns:
            raise ValidationError(
                "Obrigatório informar CPF ou CNS para o cadastro do paciente (CFM/SUS)."
            )

        if clean_cpf and len(clean_cpf) != 11:
            raise ValidationError(
                "CPF do paciente inválido: deve conter 11 dígitos numéricos."
            )

        if clean_cns and len(clean_cns) != 15:
            raise ValidationError("CNS inválido: deve conter 15 dígitos numéricos.")

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            cpf=clean_cpf,
            cns=clean_cns,
            data_nascimento=data_nascimento,
            telefone=clean_digits(telefone),
            nome_completo=nome_completo,
            nome_mae=nome_mae,
            sexo_biologico=sexo_biologico.upper() if sexo_biologico else None,
            cep=clean_digits(cep) if cep else None,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            cidade=cidade,
            estado=estado.upper() if estado else None,
            alergias=alergias or [],
        )

    def is_pediatrico(self) -> bool:
        today = date.today()
        idade = (
            today.year
            - self.data_nascimento.year
            - (
                (today.month, today.day)
                < (self.data_nascimento.month, self.data_nascimento.day)
            )
        )
        return idade < 18

    def adicionar_alergia(self, medicamento: str) -> None:
        med_clean = medicamento.strip()
        if not self.tem_alergia(med_clean):
            self.alergias = [*self.alergias, med_clean]

    def remover_alergia(self, medicamento: str) -> None:
        target = medicamento.strip().lower()
        self.alergias = [a for a in self.alergias if a.strip().lower() != target]

    def tem_alergia(self, medicamento: str) -> bool:
        target = medicamento.strip().lower()
        return any(a.strip().lower() == target for a in self.alergias)
