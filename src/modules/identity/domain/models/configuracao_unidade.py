"""Singleton clinical unit configuration model (CNES, CNPJ, IBGE, SUS mode)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.privacy import clean_digits
from src.core.uuid7 import uuid7


class ConfiguracaoUnidade(Base):
    """Configuração singleton da unidade de saúde da plataforma única MediSync.

    Substitui o modelo multi-tenant mantendo metadados SUS para BPA-I e PDF/A.
    Decisões: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md
    """

    __tablename__ = "configuracoes_unidade"
    __table_args__ = (
        UniqueConstraint("singleton_guard", name="uq_configuracoes_unidade_singleton"),
        CheckConstraint(
            "singleton_guard IS TRUE",
            name="chk_configuracoes_unidade_singleton",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    singleton_guard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(255), nullable=False)
    modo_publico_sus: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    cnes: Mapped[str | None] = mapped_column(String(7), nullable=True)
    tipo_unidade_sus: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UPA_DIGITAL_24H"
    )
    ibge_municipio: Mapped[str | None] = mapped_column(String(7), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        nome_fantasia: str,
        modo_publico_sus: bool = True,
        cnes: str | None = None,
        tipo_unidade_sus: str = "UPA_DIGITAL_24H",
        ibge_municipio: str | None = None,
        ativo: bool = True,
        singleton_guard: bool = True,
        id: UUID | None = None,
    ) -> None:
        if singleton_guard is not True:
            raise ValidationError(
                f"singleton_guard '{singleton_guard}' inválido; "
                "esperado True para garantir registro único da unidade."
            )

        digits = clean_digits(cnpj)
        if len(digits) != 14:
            raise ValidationError(
                f"CNPJ '{cnpj}' inválido: possui {len(digits)} dígitos; "
                "esperados exatamente 14 dígitos numéricos."
            )

        clean_razao = razao_social.strip()
        if not clean_razao:
            raise ValidationError(
                f"razao_social '{razao_social}' inválida; "
                "esperado nome empresarial não vazio."
            )

        clean_fantasia = nome_fantasia.strip()
        if not clean_fantasia:
            raise ValidationError(
                f"nome_fantasia '{nome_fantasia}' inválido; "
                "esperado nome fantasia não vazio."
            )

        clean_cnes = cnes.strip() if cnes and cnes.strip() else None
        if clean_cnes and len(clean_cnes) > 7:
            raise ValidationError(
                f"CNES '{cnes}' inválido; esperado código de até 7 caracteres."
            )

        clean_ibge = (
            ibge_municipio.strip()
            if ibge_municipio and ibge_municipio.strip()
            else None
        )
        if clean_ibge and len(clean_ibge) > 7:
            raise ValidationError(
                f"ibge_municipio '{ibge_municipio}' inválido; "
                "esperado código IBGE de até 7 dígitos."
            )

        now = datetime.now(UTC)
        super().__init__(
            id=id or uuid7(),
            singleton_guard=True,
            cnpj=digits,
            razao_social=clean_razao,
            nome_fantasia=clean_fantasia,
            modo_publico_sus=modo_publico_sus,
            cnes=clean_cnes,
            tipo_unidade_sus=tipo_unidade_sus.strip() or "UPA_DIGITAL_24H",
            ibge_municipio=clean_ibge,
            ativo=ativo,
            criado_em=now,
            atualizado_em=now,
        )

    def is_sus(self) -> bool:
        """Indica se a unidade opera em modo público SUS.

        Regras: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
        """
        return self.modo_publico_sus

    def ativar(self) -> None:
        """Ativa o registro da unidade na plataforma única.

        Regras: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
        """
        self.ativo = True
        self.atualizado_em = datetime.now(UTC)

    def desativar(self) -> None:
        """Desativa operacionalmente o registro da unidade na plataforma única.

        Regras: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
        """
        self.ativo = False
        self.atualizado_em = datetime.now(UTC)
