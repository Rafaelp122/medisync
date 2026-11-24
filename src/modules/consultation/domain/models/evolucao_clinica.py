"""Clinical evolution (SOAP) model for electronic health record (PEP)."""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
    Regras: RN06 (Ato Médico), CFM 2.454/2026 e consultation-domain.md.
    """

    __tablename__ = "evolucoes_clinicas"
    __table_args__ = (
        Index("idx_evolucoes_atendimento", "atendimento_id"),
        UniqueConstraint("atendimento_id", name="uq_evolucoes_clinicas_atendimento_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
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
    codigo_sigtap: Mapped[str] = mapped_column(
        String(16), default="03.01.01.025-0", nullable=False
    )
    ia_utilizada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ia_modelo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ia_sugestao_bruta: Mapped[str | None] = mapped_column(Text, nullable=True)
    ia_diff_modificacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ia_ratificada_pelo_medico: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    identidade_verificada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    tipo_documento_verificado: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    justificativa_excecao_identidade: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
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
        atendimento_id: UUID,
        medico_id: UUID,
        anamnese: str,
        conduta: str,
        *,
        exame_fisico_virtual: str | None = None,
        cid10_principal: str | None = None,
        codigo_sigtap: str = "03.01.01.025-0",
        ia_utilizada: bool = False,
        ia_modelo: str | None = None,
        ia_sugestao_bruta: str | None = None,
        ia_diff_modificacao: str | None = None,
        ia_ratificada_pelo_medico: bool = True,
        identidade_verificada: bool = False,
        tipo_documento_verificado: str | None = None,
        justificativa_excecao_identidade: str | None = None,
        registrado_em: datetime | None = None,
        finalizado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
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

        clean_tipo_doc = (
            tipo_documento_verificado.strip().upper()
            if tipo_documento_verificado and tipo_documento_verificado.strip()
            else None
        )
        clean_justificativa = (
            justificativa_excecao_identidade.strip()
            if justificativa_excecao_identidade
            and justificativa_excecao_identidade.strip()
            else None
        )

        super().__init__(
            id=id or uuid7(),
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            anamnese=anamnese.strip(),
            exame_fisico_virtual=clean_exame,
            cid10_principal=clean_cid10,
            conduta=conduta.strip(),
            codigo_sigtap=(
                codigo_sigtap.strip()
                if codigo_sigtap and codigo_sigtap.strip()
                else "03.01.01.025-0"
            ),
            ia_utilizada=ia_utilizada,
            ia_modelo=ia_modelo.strip() if ia_modelo else None,
            ia_sugestao_bruta=ia_sugestao_bruta,
            ia_diff_modificacao=ia_diff_modificacao,
            ia_ratificada_pelo_medico=ia_ratificada_pelo_medico,
            identidade_verificada=identidade_verificada,
            tipo_documento_verificado=clean_tipo_doc,
            justificativa_excecao_identidade=clean_justificativa,
            registrado_em=registrado_em or datetime.now(UTC),
            finalizado_em=finalizado_em,
        )

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

    def atualizar_soap(
        self,
        *,
        anamnese: str,
        conduta: str,
        exame_fisico_virtual: str | None = None,
        cid10_principal: str | None = None,
        codigo_sigtap: str | None = None,
        ia_utilizada: bool | None = None,
        ia_modelo: str | None = None,
        ia_sugestao_bruta: str | None = None,
        ia_diff_modificacao: str | None = None,
        ia_ratificada_pelo_medico: bool | None = None,
        identidade_verificada: bool | None = None,
        tipo_documento_verificado: str | None = None,
        justificativa_excecao_identidade: str | None = None,
    ) -> None:
        """Atualiza a anotação SOAP enquanto a consulta estiver em andamento (RN06).

        Garante integridade clínica sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico), CFM 2.454/2026 e consultation-domain.md.
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
        if codigo_sigtap is not None and codigo_sigtap.strip():
            self.codigo_sigtap = codigo_sigtap.strip()
        if ia_utilizada is not None:
            self.ia_utilizada = ia_utilizada
        if ia_modelo is not None:
            self.ia_modelo = ia_modelo.strip() if ia_modelo else None
        if ia_sugestao_bruta is not None:
            self.ia_sugestao_bruta = ia_sugestao_bruta
        if ia_diff_modificacao is not None:
            self.ia_diff_modificacao = ia_diff_modificacao
        if ia_ratificada_pelo_medico is not None:
            self.ia_ratificada_pelo_medico = ia_ratificada_pelo_medico
        if identidade_verificada is not None:
            self.identidade_verificada = identidade_verificada
        if tipo_documento_verificado is not None:
            self.tipo_documento_verificado = (
                tipo_documento_verificado.strip().upper()
                if tipo_documento_verificado.strip()
                else None
            )
        if justificativa_excecao_identidade is not None:
            self.justificativa_excecao_identidade = (
                justificativa_excecao_identidade.strip()
                if justificativa_excecao_identidade.strip()
                else None
            )
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
