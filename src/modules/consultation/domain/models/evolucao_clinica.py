"""Clinical evolution (SOAP) model for electronic health record (PEP)."""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.uuid7 import uuid7
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
)

_CID10_REGEX = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,2})?$")
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class EvolucaoClinica(Base):
    """Clinical evolution aggregate entity storing medical SOAP notes."""

    __tablename__ = "evolucoes_clinicas"
    __table_args__ = (
        Index("idx_evolucoes_atendimento", "atendimento_id"),
        Index("idx_evolucoes_org", "organizacao_id"),
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
    medico_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=False,
    )
    anamnese: Mapped[str] = mapped_column(Text, nullable=False)
    exame_fisico_virtual: Mapped[str | None] = mapped_column(Text, nullable=True)
    cid10_principal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    conduta: Mapped[str] = mapped_column(Text, nullable=False)
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        medico_id: UUID,
        anamnese: str,
        conduta: str,
        *,
        exame_fisico_virtual: str | None = None,
        cid10_principal: str | None = None,
        registrado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ConsultaInvalidaError(
                "organizacao_id inválido: deve ser um identificador positivo."
            )

        if not anamnese or not anamnese.strip():
            raise ConsultaInvalidaError(
                "Anamnese clínica é obrigatória e não pode ser vazia."
            )

        if not conduta or not conduta.strip():
            raise ConsultaInvalidaError(
                "Conduta clínica é obrigatória e não pode ser vazia."
            )

        clean_cid10: str | None = None
        if cid10_principal is not None and cid10_principal.strip():
            c = cid10_principal.strip().upper()
            if not _CID10_REGEX.match(c):
                raise ConsultaInvalidaError(
                    f"Código CID-10 inválido: '{cid10_principal}'. "
                    "Formato esperado: letra maiúscula seguida de 2 dígitos "
                    "e subcategoria opcional (ex.: J00, J02.9, A09.0)."
                )
            clean_cid10 = c

        clean_exame = (
            exame_fisico_virtual.strip()
            if exame_fisico_virtual and exame_fisico_virtual.strip()
            else None
        )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            anamnese=anamnese.strip(),
            exame_fisico_virtual=clean_exame,
            cid10_principal=clean_cid10,
            conduta=conduta.strip(),
            registrado_em=registrado_em or datetime.now(UTC),
        )
        self._is_finalizado: bool = False

    @property
    def is_finalizado(self) -> bool:
        """Indicate whether the clinical consultation was marked as finalized."""
        return getattr(self, "_is_finalizado", False)

    def marcar_finalizado(self) -> None:
        """Lock the clinical record preventing further edits or deletion."""
        self._is_finalizado = True

    def validar_pode_excluir(self, status_atendimento: str | None = None) -> None:
        """Check if deletion is permitted based on consultation status.

        Under CFM regulations and PEP immutability, finalized attendance records
        cannot be deleted or mutated.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                "Não é permitido excluir evolução de consulta finalizada."
            )

        if status_atendimento is not None:
            status_clean = str(status_atendimento).strip().upper()
            if status_clean in _STATUS_TERMINAIS:
                raise ConsultaFinalizadaError(
                    "Não é permitido excluir evolução de consulta finalizada "
                    f"(status terminal '{status_clean}')."
                )


@event.listens_for(EvolucaoClinica, "before_delete")
def impedir_exclusao_evolucao_finalizada(
    _mapper: Any, _connection: Any, target: EvolucaoClinica
) -> None:
    if target.is_finalizado:
        raise ConsultaFinalizadaError(
            "Não é permitido excluir evolução de consulta finalizada."
        )
