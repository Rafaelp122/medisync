"""Attendance aggregate root and lifecycle state machine (RN03)."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.queue.domain.enums import (
    TERMINAL_STATUSES,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError

_HEX64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


def _validar_tcle_hash(hash_str: str) -> str:
    cleaned = hash_str.strip()
    if not _HEX64_REGEX.match(cleaned):
        raise ValidationError(
            f"Hash do TCLE '{hash_str}' inválido: deve conter 64 caracteres "
            "hexadecimais (SHA-256)."
        )
    return cleaned.lower()


class Atendimento(Base):
    """Raiz de agregado do atendimento clínico governando o ciclo de vida.

    Garante score 64-bit (RN01), lock 45s (RN02) e backpressure (RN05).
    Regras: docs/explanation/domains/queue-domain.md
    ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    História: docs/user-stories/US-07-alocacao-chamada-medica.md
    """

    __tablename__ = "atendimentos"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'TRIADO_AGUARDANDO_ELEGIBILIDADE', "
            "'APTO_PARA_CHAMADA', "
            "'CHAMANDO_PACIENTE', "
            "'EM_ATENDIMENTO', "
            "'PACIENTE_AUSENTE', "
            "'CONCLUIDO', "
            "'CANCELADO_PACIENTE'"
            ")",
            name="chk_atendimento_status",
        ),
        CheckConstraint(
            "prioridade_clinica BETWEEN 1 AND 5",
            name="chk_atendimento_prioridade",
        ),
        Index("idx_atendimentos_org_status", "organizacao_id", "status"),
        Index("idx_atendimentos_org_paciente", "organizacao_id", "paciente_id"),
        Index("idx_atendimentos_medico", "medico_id"),
        Index(
            "idx_atendimentos_fila",
            "organizacao_id",
            "status",
            "prioridade_clinica",
            "data_entrada_fila",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    paciente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    medico_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        nullable=False,
    )
    prioridade_clinica: Mapped[int] = mapped_column(
        Integer,
        default=PrioridadeClinica.NAO_URGENTE,
        nullable=False,
    )
    tcle_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_entrada_fila: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    chamada_iniciada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    chamada_finalizada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
        organizacao_id: int,
        paciente_id: UUID,
        *,
        medico_id: UUID | None = None,
        status: (
            StatusAtendimento | str
        ) = StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica: int | PrioridadeClinica = PrioridadeClinica.NAO_URGENTE,
        tcle_hash: str | None = None,
        data_entrada_fila: datetime | None = None,
        chamada_iniciada_em: datetime | None = None,
        chamada_finalizada_em: datetime | None = None,
        criado_em: datetime | None = None,
        atualizado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ValidationError(
                f"organizacao_id '{organizacao_id}' inválido; "
                "deve ser um identificador positivo > 0."
            )

        prioridade_int = int(prioridade_clinica)
        if prioridade_int < 1 or prioridade_int > 5:
            raise ValidationError(
                f"Prioridade clínica '{prioridade_int}' inválida; esperado valor "
                "entre 1 e 5 (1=Emergência, 5=Não Urgente)."
            )

        clean_tcle: str | None = None
        if tcle_hash is not None:
            clean_tcle = _validar_tcle_hash(tcle_hash)

        status_str = str(status)

        super_kwargs: dict[str, object] = {
            "id": id or uuid7(),
            "organizacao_id": organizacao_id,
            "paciente_id": paciente_id,
            "medico_id": medico_id,
            "status": status_str,
            "prioridade_clinica": prioridade_int,
            "tcle_hash": clean_tcle,
            "data_entrada_fila": data_entrada_fila,
            "chamada_iniciada_em": chamada_iniciada_em,
            "chamada_finalizada_em": chamada_finalizada_em,
        }
        if criado_em is not None:
            super_kwargs["criado_em"] = criado_em
        if atualizado_em is not None:
            super_kwargs["atualizado_em"] = atualizado_em

        super().__init__(**super_kwargs)

    # -------------------------------------------------------------------------
    # Transições da Máquina de Estados Finita (RN03)
    # -------------------------------------------------------------------------

    def promover_para_apto(self) -> None:
        """Transiciona para APTO_PARA_CHAMADA preservando antiguidade na fila.

        Regras: RN01 (Score Imutável de Antiguidade), RN03 (Transição Apto), NC-QUE-04.
        Regras: docs/explanation/domains/queue-domain.md
        História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
        """
        self._assegurar_nao_finalizado()
        if self.status != StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos em "
                f"'{StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE}' "
                f"podem ser promovidos para apto. Estado atual: '{self.status}'."
            )

        if self.tcle_hash is None:
            raise ValidationError(
                f"Atendimento '{self.id}' não pode ser promovido para apto sem "
                "consentimento do TCLE (tcle_hash ausente)."
            )

        now = datetime.now(UTC)
        self.status = StatusAtendimento.APTO_PARA_CHAMADA.value
        self.data_entrada_fila = (
            self.data_entrada_fila or getattr(self, "criado_em", None) or now
        )
        self.atualizado_em = now

    def iniciar_chamada(self, medico_id: UUID) -> None:
        """Aloca médico e transiciona para CHAMANDO_PACIENTE com lock 45s (RN02, RN03).

        Regras: docs/explanation/domains/queue-domain.md
        ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        """
        self._assegurar_nao_finalizado()
        if not medico_id:
            raise ValidationError(
                "Médico responsável é obrigatório para iniciar a chamada. "
                f"Valor recebido: '{medico_id}'."
            )

        if self.status != StatusAtendimento.APTO_PARA_CHAMADA:
            msg = (
                f"Apenas atendimentos em '{StatusAtendimento.APTO_PARA_CHAMADA}' "
                f"podem ser chamados. Estado atual: '{self.status}'."
            )
            raise TransicaoEstadoInvalidaError(msg)

        now = datetime.now(UTC)
        self.medico_id = medico_id
        self.status = StatusAtendimento.CHAMANDO_PACIENTE.value
        self.chamada_iniciada_em = now
        self.atualizado_em = now

    def atender_chamada(self) -> None:
        """Paciente conecta à videochamada e transiciona para EM_ATENDIMENTO (RN03).

        Regras: docs/explanation/domains/queue-domain.md
        """
        self._assegurar_nao_finalizado()
        if self.status != StatusAtendimento.CHAMANDO_PACIENTE:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos em '{StatusAtendimento.CHAMANDO_PACIENTE}' "
                f"podem ser atendidos. Estado atual: '{self.status}'."
            )

        now = datetime.now(UTC)
        self.status = StatusAtendimento.EM_ATENDIMENTO.value
        self.atualizado_em = now

    def registrar_ausencia_paciente(self) -> None:
        """Timeout de toque (45s sem resposta): vai para PACIENTE_AUSENTE (RN02).

        Regras: docs/explanation/domains/queue-domain.md
        ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        """
        self._assegurar_nao_finalizado()
        if self.status != StatusAtendimento.CHAMANDO_PACIENTE:
            raise TransicaoEstadoInvalidaError(
                f"Apenas chamadas ativas em '{StatusAtendimento.CHAMANDO_PACIENTE}' "
                f"podem registrar ausência do paciente. Estado atual: '{self.status}'."
            )

        now = datetime.now(UTC)
        self.status = StatusAtendimento.PACIENTE_AUSENTE.value
        self.chamada_finalizada_em = now
        self.atualizado_em = now

    def concluir_atendimento(self) -> None:
        """Médico finaliza a teleconsulta e transiciona para CONCLUIDO (RN03).

        Regras: docs/explanation/domains/queue-domain.md
        """
        self._assegurar_nao_finalizado()
        if self.status != StatusAtendimento.EM_ATENDIMENTO:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos no estado '{StatusAtendimento.EM_ATENDIMENTO}' "
                f"podem ser concluídos. Estado atual: '{self.status}'."
            )

        now = datetime.now(UTC)
        self.status = StatusAtendimento.CONCLUIDO.value
        self.chamada_finalizada_em = now
        self.atualizado_em = now

    def cancelar_pelo_paciente(self, motivo: str | None = None) -> None:
        """Registra desistência do paciente antes da consulta clínica (RN03).

        Regras: docs/explanation/domains/queue-domain.md
        """
        self._assegurar_nao_finalizado()
        if self.status == StatusAtendimento.EM_ATENDIMENTO:
            raise TransicaoEstadoInvalidaError(
                "Não é possível cancelar atendimento já em andamento clínico. "
                f"Estado atual: '{self.status}'."
            )

        permitidos = (
            StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            StatusAtendimento.APTO_PARA_CHAMADA,
            StatusAtendimento.CHAMANDO_PACIENTE,
        )
        if self.status not in permitidos:
            permitidos_str = ", ".join(f"'{s}'" for s in permitidos)
            raise TransicaoEstadoInvalidaError(
                f"Estado '{self.status}' não permite cancelamento pelo paciente; "
                f"esperados: [{permitidos_str}]."
            )

        now = datetime.now(UTC)
        if self.status == StatusAtendimento.CHAMANDO_PACIENTE:
            self.chamada_finalizada_em = now
        self.status = StatusAtendimento.CANCELADO_PACIENTE.value
        self.atualizado_em = now

    # -------------------------------------------------------------------------
    # Regras Clínicas Adicionais (RN-REG-01 e Valkey Queue Score)
    # -------------------------------------------------------------------------

    def atualizar_prioridade(self, nova_prioridade: int | PrioridadeClinica) -> None:
        """Soberania diagnóstica do médico assistente (RN01, RN-REG-01).

        Regras: docs/explanation/domains/queue-domain.md
        """
        self._assegurar_nao_finalizado()
        prioridade_int = int(nova_prioridade)
        if prioridade_int < 1 or prioridade_int > 5:
            raise ValidationError(
                f"Prioridade clínica '{prioridade_int}' inválida; esperado valor "
                "entre 1 e 5 (1=Emergência, 5=Não Urgente)."
            )
        self.prioridade_clinica = prioridade_int
        self.atualizado_em = datetime.now(UTC)

    def _assegurar_nao_finalizado(self) -> None:
        if self.is_finalizado:
            raise TransicaoEstadoInvalidaError(
                f"Atendimento já finalizado no estado '{self.status}'."
            )

    # -------------------------------------------------------------------------
    # Helpers de Domínio e Consulta
    # -------------------------------------------------------------------------

    @property
    def is_em_fila(self) -> bool:
        return self.status in (
            StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            StatusAtendimento.APTO_PARA_CHAMADA,
        )

    @property
    def is_apto_para_chamada(self) -> bool:
        return self.status == StatusAtendimento.APTO_PARA_CHAMADA

    @property
    def is_chamando(self) -> bool:
        return self.status == StatusAtendimento.CHAMANDO_PACIENTE

    @property
    def is_em_atendimento(self) -> bool:
        return self.status == StatusAtendimento.EM_ATENDIMENTO

    @property
    def is_ativo(self) -> bool:
        return self.status in (
            StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            StatusAtendimento.APTO_PARA_CHAMADA,
            StatusAtendimento.CHAMANDO_PACIENTE,
            StatusAtendimento.EM_ATENDIMENTO,
        )

    @property
    def is_finalizado(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def tempo_espera_segundos(self) -> float | None:
        if self.data_entrada_fila and self.chamada_iniciada_em:
            return (self.chamada_iniciada_em - self.data_entrada_fila).total_seconds()
        return None

    @property
    def duracao_chamada_segundos(self) -> float | None:
        if self.chamada_iniciada_em and self.chamada_finalizada_em:
            return (
                self.chamada_finalizada_em - self.chamada_iniciada_em
            ).total_seconds()
        return None
