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
    UniqueConstraint,
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
    """Registro de evolução clínica estruturada SOAP do Prontuário Eletrônico.

    Garante imutabilidade sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
    Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
    """

    __tablename__ = "evolucoes_clinicas"
    __table_args__ = (
        Index("idx_evolucoes_atendimento", "atendimento_id"),
        Index("idx_evolucoes_org", "organizacao_id"),
        UniqueConstraint("atendimento_id", name="uq_evolucoes_clinicas_atendimento_id"),
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
    finalizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
        finalizado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ConsultaInvalidaError(
                f"organizacao_id inválido: {organizacao_id}; "
                "deve ser um identificador positivo (> 0)."
            )

        if not anamnese or not anamnese.strip():
            raise ConsultaInvalidaError(
                f"Anamnese clínica é obrigatória e não pode ser vazia: {anamnese!r}."
            )

        if not conduta or not conduta.strip():
            raise ConsultaInvalidaError(
                f"Conduta clínica é obrigatória e não pode ser vazia: {conduta!r}."
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
            finalizado_em=finalizado_em,
        )
        self._is_finalizado: bool = finalizado_em is not None

    @property
    def is_finalizado(self) -> bool:
        """Indica se a consulta atingiu o estado terminal e teve PEP bloqueado.

        Assegura imutabilidade legal do registro após encerramento (CFM nº 1.821/2007).
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        return self.finalizado_em is not None

    def marcar_finalizado(self) -> None:
        """Congela a evolução clínica e registra data/hora final de atendimento.

        Inviabiliza adulterações posteriores conforme CFM nº 1.821/2007 e LGPD Art. 16.
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        self.finalizado_em = datetime.now(UTC)
        self._is_finalizado = True

    def atualizar_soap(
        self,
        *,
        anamnese: str,
        conduta: str,
        exame_fisico_virtual: str | None = None,
        cid10_principal: str | None = None,
    ) -> None:
        """Atualiza a anotação SOAP enquanto a consulta estiver em andamento (RN06).

        Garante integridade clínica sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                f"Não é permitido atualizar evolução '{self.id}' "
                "de consulta finalizada (is_finalizado=True)."
            )
        if not anamnese or not anamnese.strip():
            raise ConsultaInvalidaError(
                f"Anamnese clínica é obrigatória e não pode ser vazia: {anamnese!r}."
            )
        if not conduta or not conduta.strip():
            raise ConsultaInvalidaError(
                f"Conduta clínica é obrigatória e não pode ser vazia: {conduta!r}."
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

        self.anamnese = anamnese.strip()
        self.conduta = conduta.strip()
        self.exame_fisico_virtual = (
            exame_fisico_virtual.strip()
            if exame_fisico_virtual and exame_fisico_virtual.strip()
            else None
        )
        self.cid10_principal = clean_cid10
        self.registrado_em = datetime.now(UTC)

    def validar_pode_excluir(self, status_atendimento: str | None = None) -> None:
        """Valida se a exclusão da evolução é legalmente admissível.

        Veda exclusão de registros após conclusão clínica sob CFM nº 1.821/2007 e RN06.
        Regras: docs/explanation/domains/consultation-domain.md.
        """
        if self.is_finalizado:
            raise ConsultaFinalizadaError(
                f"Não é permitido excluir evolução '{self.id}' de consulta finalizada "
                "(is_finalizado=True)."
            )

        if status_atendimento is not None:
            status_clean = str(status_atendimento).strip().upper()
            if status_clean in _STATUS_TERMINAIS:
                raise ConsultaFinalizadaError(
                    f"Não é permitido excluir evolução '{self.id}' de consulta "
                    f"finalizada (status terminal: '{status_clean}'; "
                    f"terminais: {sorted(_STATUS_TERMINAIS)})."
                )


@event.listens_for(EvolucaoClinica, "before_delete")
def impedir_exclusao_evolucao_finalizada(
    _mapper: Any, _connection: Any, target: EvolucaoClinica
) -> None:
    """Impede deleção física de evolução clínica finalizada no banco.

    Garante conformidade com o Art. 11 da CFM 1.821/2007 sobre guarda do PEP.
    Regras: docs/explanation/domains/consultation-domain.md.
    """
    if target.is_finalizado:
        raise ConsultaFinalizadaError(
            f"Não é permitido excluir evolução clínica '{target.id}' "
            "de consulta finalizada (is_finalizado=True)."
        )
