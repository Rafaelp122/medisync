"""Clinical triage aggregate model with risk priority and emergency flag."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.uuid7 import uuid7
from src.modules.triage.domain.exceptions import TriagemInvalidaError


class Triagem(Base):
    """Clinical triage record associated 1:1 with an attendance."""

    __tablename__ = "triagens"
    __table_args__ = (
        CheckConstraint(
            "prioridade_calculada BETWEEN 1 AND 5",
            name="chk_triagem_prioridade",
        ),
        Index("idx_triagens_org", "organizacao_id"),
        Index("idx_triagens_atendimento", "atendimento_id"),
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
        unique=True,
        nullable=False,
    )
    queixa_principal: Mapped[str] = mapped_column(Text, nullable=False)
    sintomas_alerta: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    alerta_samu_disparado: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    prioridade_calculada: Mapped[int] = mapped_column(Integer, nullable=False)
    avaliado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        queixa_principal: str,
        prioridade_calculada: int,
        *,
        sintomas_alerta: list[str] | None = None,
        alerta_samu_disparado: bool = False,
        avaliado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise TriagemInvalidaError(
                "organizacao_id inválido: deve ser um identificador positivo."
            )

        if not queixa_principal or not queixa_principal.strip():
            raise TriagemInvalidaError("Queixa principal não pode ser vazia.")

        prioridade_int = int(prioridade_calculada)
        if prioridade_int < 1 or prioridade_int > 5:
            raise TriagemInvalidaError(
                "Prioridade calculada deve ser entre 1 e 5 "
                "(1=Emergência, 5=Não Urgente)."
            )

        clean_sintomas = [
            s.strip().lower() for s in (sintomas_alerta or []) if s and s.strip()
        ]

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            queixa_principal=queixa_principal.strip(),
            sintomas_alerta=clean_sintomas,
            alerta_samu_disparado=alerta_samu_disparado,
            prioridade_calculada=prioridade_int,
            avaliado_em=avaliado_em or datetime.now(UTC),
        )

    def disparar_alerta_samu(self) -> None:
        """Sinaliza a salvaguarda de deterioração e redirecionamento SAMU 192 (RN04)."""
        self.alerta_samu_disparado = True

    def adicionar_sintoma_alerta(self, sintoma: str) -> None:
        """Adiciona um novo sintoma de alerta à lista, evitando duplicidades."""
        cleaned = sintoma.strip().lower()
        if cleaned and cleaned not in self.sintomas_alerta:
            self.sintomas_alerta = [*self.sintomas_alerta, cleaned]

    @property
    def is_emergencia_critica(self) -> bool:
        """Indica se a triagem configura emergência de nível 1 com risco à vida."""
        return self.prioridade_calculada == 1 or self.alerta_samu_disparado
