"""Tenant organization model (municipalities, clinics, healthcare networks)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.modules.identity.domain.models._helpers import clean_digits


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
        digits = clean_digits(cnpj)
        if len(digits) != 14:
            raise ValidationError(
                "CNPJ inválido: deve conter exatamente 14 dígitos numéricos."
            )

        super().__init__(
            cnpj=digits,
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
