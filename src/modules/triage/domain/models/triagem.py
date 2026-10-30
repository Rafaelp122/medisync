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
from src.modules.triage.domain.classification import classificar_risco_clinico
from src.modules.triage.domain.exceptions import TriagemInvalidaError


class Triagem(Base):
    """Registro clínico de triagem associado 1:1 ao atendimento do paciente.

    Governa detecção de risco com salvaguarda SAMU 192 (RN04) e auditoria TCLE (RN07).
    Regras: docs/explanation/domains/triage-domain.md.
    História: docs/user-stories/US-01-acolhimento-triagem-tcle.md.
    """

    __tablename__ = "triagens"
    __table_args__ = (
        CheckConstraint(
            "prioridade_calculada BETWEEN 1 AND 5",
            name="chk_triagem_prioridade",
        ),
        CheckConstraint(
            "escala_dor BETWEEN 0 AND 10",
            name="chk_triagem_escala_dor",
        ),
        Index("idx_triagens_org", "organizacao_id"),
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
    escala_dor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
        escala_dor: int = 0,
        sintomas_alerta: list[str] | None = None,
        alerta_samu_disparado: bool = False,
        avaliado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise TriagemInvalidaError(
                f"organizacao_id '{organizacao_id}' inválido; "
                "deve ser um identificador positivo > 0."
            )

        if not queixa_principal or not queixa_principal.strip():
            raise TriagemInvalidaError(
                f"Queixa principal '{queixa_principal}' não pode ser vazia; "
                "esperado texto descritivo preenchido."
            )

        prioridade_int = int(prioridade_calculada)
        if prioridade_int < 1 or prioridade_int > 5:
            raise TriagemInvalidaError(
                f"Prioridade calculada '{prioridade_int}' inválida; "
                "esperado valor entre 1 e 5."
            )

        escala_dor_int = int(escala_dor)
        if escala_dor_int < 0 or escala_dor_int > 10:
            raise TriagemInvalidaError(
                f"Escala de dor '{escala_dor_int}' inválida; "
                "esperado valor entre 0 e 10."
            )

        clean_sintomas = [
            s.strip().lower() for s in (sintomas_alerta or []) if s and s.strip()
        ]

        prioridade_esperada = classificar_risco_clinico(
            queixa_principal.strip(), clean_sintomas, escala_dor_int
        )
        if prioridade_int != prioridade_esperada:
            raise TriagemInvalidaError(
                f"Prioridade calculada '{prioridade_int}' incoerente com a queixa "
                f"e sintomas informados; esperado '{prioridade_esperada}'."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            queixa_principal=queixa_principal.strip(),
            sintomas_alerta=clean_sintomas,
            escala_dor=escala_dor_int,
            alerta_samu_disparado=alerta_samu_disparado,
            prioridade_calculada=prioridade_int,
            avaliado_em=avaliado_em or datetime.now(UTC),
        )

    def disparar_alerta_samu(self) -> None:
        """Sinaliza a salvaguarda de deterioração e redirecionamento SAMU 192 (RN04).

        Regras: docs/explanation/domains/triage-domain.md
        """
        self.alerta_samu_disparado = True

    def adicionar_sintoma_alerta(self, sintoma: str) -> None:
        """Adiciona um novo sintoma de alerta à lista, evitando duplicidades (RN04).

        Regras: docs/explanation/domains/triage-domain.md
        """
        cleaned = sintoma.strip().lower()
        if cleaned and cleaned not in self.sintomas_alerta:
            self.sintomas_alerta = [*self.sintomas_alerta, cleaned]

    @property
    def is_emergencia_critica(self) -> bool:
        """Indica se a triagem configura emergência de nível 1 com risco à vida (RN04).

        Regras: docs/explanation/domains/triage-domain.md
        """
        return self.prioridade_calculada == 1 or self.alerta_samu_disparado
