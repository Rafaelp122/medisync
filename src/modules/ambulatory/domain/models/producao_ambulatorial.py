"""Ambulatory production model for SUS BPA-I and SISAB reporting (ADR-012)."""

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
from src.core.uuid7 import uuid7


class ProducaoAmbulatorial(Base):
    """Registro de produção ambulatorial individualizada (BPA-I / SISAB) no SUS.

    Representa o procedimento ambulatorial consolidado após a teleconsulta para
    faturamento público junto ao Ministério da Saúde (SIGTAP 03.01.01.025-0).
    Conforme ADR-012, Portaria GM/MS nº 3.232/2024 e US-11.
    """

    __tablename__ = "producoes_ambulatoriais"
    __table_args__ = (
        Index("idx_producao_atendimento", "atendimento_id"),
        Index("idx_producao_org", "organizacao_id"),
        Index("idx_producao_competencia", "competencia"),
        UniqueConstraint(
            "atendimento_id", name="uq_producoes_ambulatoriais_atendimento_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    atendimento_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("atendimentos.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profissional_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=False,
    )
    paciente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cnes: Mapped[str] = mapped_column(String(7), nullable=False)
    codigo_sigtap: Mapped[str] = mapped_column(
        String(16), nullable=False, default="03.01.01.025-0"
    )
    carater_atendimento: Mapped[str] = mapped_column(
        String(2), nullable=False, default="02"
    )
    competencia: Mapped[str] = mapped_column(String(6), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CONSOLIDADO"
    )
    consolidado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def __init__(
        self,
        *,
        organizacao_id: int,
        atendimento_id: UUID,
        profissional_id: UUID,
        paciente_id: UUID,
        cnes: str,
        codigo_sigtap: str = "03.01.01.025-0",
        carater_atendimento: str = "02",
        competencia: str | None = None,
        consolidado_em: datetime | None = None,
    ) -> None:
        """Inicializa registro de produção ambulatorial validando restrições do SUS."""
        cnes_limpo = cnes.strip()
        if not cnes_limpo or len(cnes_limpo) > 7:
            raise ValueError(
                f"CNES '{cnes}' inválido; esperado código numérico de até 7 dígitos."
            )

        now = consolidado_em or datetime.now(UTC)
        comp = competencia or now.strftime("%Y%m")

        super().__init__(
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            profissional_id=profissional_id,
            paciente_id=paciente_id,
            cnes=cnes_limpo,
            codigo_sigtap=codigo_sigtap,
            carater_atendimento=carater_atendimento,
            competencia=comp,
            status="CONSOLIDADO",
            consolidado_em=now,
        )
