"""Identity Bounded Context rich domain models (SQLAlchemy 2.0)."""

import re
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.security import hash_password, verify_password
from src.core.uuid7 import uuid7

PapelProfissional = Literal["ADMIN_GLOBAL", "GESTOR_UNIDADE", "MEDICO", "FATURAMENTO"]


def _clean_digits(val: str) -> str:
    return re.sub(r"\D", "", val)


class Organizacao(Base):
    """Tenant model representing municipalities or private healthcare institutions."""

    __tablename__ = "organizacoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cnpj: Mapped[str] = mapped_column(String(18), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(255), nullable=False)
    modo_publico_sus: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    config_plantao: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "alpha_margem": 1.25,
            "tma_estimado_segundos": 600,
            "cota_diaria_maxima": 300,
        },
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        nome_fantasia: str,
        modo_publico_sus: bool = False,
        config_plantao: dict[str, Any] | None = None,
        ativo: bool = True,
        id: int | None = None,
    ) -> None:
        clean_cnpj = _clean_digits(cnpj)
        if len(clean_cnpj) != 14:
            raise ValidationError(
                "CNPJ inválido: deve conter exatamente 14 dígitos numéricos."
            )

        super().__init__(
            cnpj=clean_cnpj,
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            modo_publico_sus=modo_publico_sus,
            config_plantao=config_plantao
            or {
                "alpha_margem": 1.25,
                "tma_estimado_segundos": 600,
                "cota_diaria_maxima": 300,
            },
            ativo=ativo,
        )
        if id is not None:
            self.id = id

    def is_sus(self) -> bool:
        return self.modo_publico_sus

    def ativar(self) -> None:
        self.ativo = True

    def desativar(self) -> None:
        self.ativo = False


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
        clean_cpf = _clean_digits(cpf)
        if len(clean_cpf) != 11:
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
            cpf=clean_cpf,
            nome_completo=nome_completo,
            email=email.strip().lower(),
            senha_hash=senha_hash,
            papel=papel,
            crm=crm.strip() if crm else None,
            crm_uf=crm_uf.strip().upper() if crm_uf else None,
            ativo=ativo,
        )

    def is_medico(self) -> bool:
        return self.papel == "MEDICO"

    def set_password(self, plain_password: str) -> None:
        """Hash and update password using Argon2id."""
        self.senha_hash = hash_password(plain_password)

    def verify_password(self, plain_password: str) -> bool:
        """Verify password against stored Argon2id hash."""
        return verify_password(plain_password, self.senha_hash)

    def ativar(self) -> None:
        self.ativo = True

    def desativar(self) -> None:
        self.ativo = False


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
        clean_cpf = _clean_digits(cpf) if cpf else None
        clean_cns = _clean_digits(cns) if cns else None

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
            telefone=_clean_digits(telefone),
            nome_completo=nome_completo,
            nome_mae=nome_mae,
            sexo_biologico=sexo_biologico.upper() if sexo_biologico else None,
            cep=_clean_digits(cep) if cep else None,
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
