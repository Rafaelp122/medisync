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
    """Modelo clínico de paciente para acolhimento progressivo em 2 fases.

    Regras: RN07 (TCLE), LGPD Art. 11 (dados sensíveis), CFM 1.821/2007 (prontuário).
    Documentação: docs/explanation/domains/identity-domain.md
    """

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
    nome_social: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        nome_social: str | None = None,
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

        clean_sexo = sexo_biologico.strip().upper() if sexo_biologico else None
        if clean_sexo and clean_sexo not in ("M", "F"):
            raise ValidationError(
                f"Sexo biológico '{sexo_biologico}' inválido; esperado 'M' ou 'F'."
            )

        clean_estado = estado.strip().upper() if estado else None
        if clean_estado and len(clean_estado) != 2:
            raise ValidationError(
                f"Estado (UF) '{estado}' inválido; esperado sigla com 2 caracteres."
            )

        clean_cep = clean_digits(cep) if cep else None
        if clean_cep and len(clean_cep) != 8:
            raise ValidationError(
                f"CEP '{cep}' inválido; esperado formato com 8 dígitos."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            cpf=clean_cpf,
            cns=clean_cns,
            data_nascimento=data_nascimento,
            telefone=clean_digits(telefone),
            nome_completo=nome_completo.strip() if nome_completo else None,
            nome_social=nome_social.strip() if nome_social else None,
            nome_mae=nome_mae.strip() if nome_mae else None,
            sexo_biologico=clean_sexo,
            cep=clean_cep,
            logradouro=logradouro.strip() if logradouro else None,
            numero=numero.strip() if numero else None,
            bairro=bairro.strip() if bairro else None,
            cidade=cidade.strip() if cidade else None,
            estado=clean_estado,
            alergias=alergias or [],
        )

    def completar_fase_2(
        self,
        *,
        nome_mae: str,
        sexo_biologico: str,
        cep: str,
        logradouro: str,
        numero: str,
        bairro: str,
        cidade: str,
        estado: str,
        nome_social: str | None = None,
        alergias: list[str] | None = None,
    ) -> None:
        """Completa o cadastro clínico regulatório da Fase 2 (CFM 1.821/2007).

        Regras: docs/explanation/domains/identity-domain.md
        História: docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
        """
        if not nome_mae or not nome_mae.strip():
            raise ValidationError(
                f"Nome da mãe '{nome_mae}' não pode ser vazio; "
                "campo obrigatório conforme CFM 1.821/2007."
            )

        clean_sexo = sexo_biologico.strip().upper()
        if clean_sexo not in ("M", "F"):
            raise ValidationError(
                f"Sexo biológico '{sexo_biologico}' inválido; esperado 'M' ou 'F'."
            )

        clean_cep = clean_digits(cep)
        if len(clean_cep) != 8:
            raise ValidationError(
                f"CEP '{cep}' inválido; esperado formato com 8 dígitos."
            )

        if not logradouro or not logradouro.strip():
            raise ValidationError(
                f"Logradouro '{logradouro}' não pode ser vazio; "
                "esperado texto descritivo."
            )
        if not numero or not numero.strip():
            raise ValidationError(
                f"Número do endereço '{numero}' não pode ser vazio; "
                "esperado identificador predial."
            )
        if not bairro or not bairro.strip():
            raise ValidationError(
                f"Bairro '{bairro}' não pode ser vazio; esperado nome de bairro."
            )
        if not cidade or not cidade.strip():
            raise ValidationError(
                f"Cidade '{cidade}' não pode ser vazia; esperado nome do município."
            )

        clean_uf = estado.strip().upper()
        if len(clean_uf) != 2:
            raise ValidationError(
                f"Sigla de estado (UF) '{estado}' inválida; "
                "esperado exatamente 2 caracteres."
            )

        self.nome_mae = nome_mae.strip()
        self.sexo_biologico = clean_sexo
        self.cep = clean_cep
        self.logradouro = logradouro.strip()
        self.numero = numero.strip()
        self.bairro = bairro.strip()
        self.cidade = cidade.strip()
        self.estado = clean_uf

        if nome_social is not None and nome_social.strip():
            self.nome_social = nome_social.strip()

        if alergias:
            clean_alergias = [a.strip() for a in alergias if a.strip()]
            self.alergias = clean_alergias

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
