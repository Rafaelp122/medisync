"""Attendance aggregate root and lifecycle state machine (RN03)."""

import re
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
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
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError

_HEX64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


class StatusAtendimento(StrEnum):
    """Deterministic states of clinical attendance lifecycle (RN03)."""

    TRIADO_AGUARDANDO_ELEGIBILIDADE = "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    APTO_PARA_CHAMADA = "APTO_PARA_CHAMADA"
    CHAMANDO_PACIENTE = "CHAMANDO_PACIENTE"
    EM_ATENDIMENTO = "EM_ATENDIMENTO"
    PACIENTE_AUSENTE = "PACIENTE_AUSENTE"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO_PACIENTE = "CANCELADO_PACIENTE"


class PrioridadeClinica(IntEnum):
    """Clinical urgency triage levels (RN01 / Acolhimento ACR)."""

    EMERGENCIA = 1  # Vermelho - Risco Iminente
    MUITO_URGENTE = 2  # Laranja - Alta Gravidade
    URGENTE = 3  # Amarelo - Moderada Gravidade
    POUCO_URGENTE = 4  # Verde - Baixa Gravidade
    NAO_URGENTE = 5  # Azul - Eletivo / Não Urgente


TERMINAL_STATUSES = frozenset(
    {
        StatusAtendimento.CONCLUIDO,
        StatusAtendimento.PACIENTE_AUSENTE,
        StatusAtendimento.CANCELADO_PACIENTE,
    }
)


class Atendimento(Base):
    """Attendance aggregate root governing the patient lifecycle."""

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
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ValidationError(
                "organizacao_id inválido: deve ser um identificador positivo."
            )

        prioridade_int = int(prioridade_clinica)
        if prioridade_int < 1 or prioridade_int > 5:
            raise ValidationError(
                "Prioridade clínica deve ser entre 1 e 5 (1=Emergência, 5=Não Urgente)."
            )

        clean_tcle: str | None = None
        if tcle_hash is not None:
            clean_tcle = self._validar_formato_tcle(tcle_hash)

        status_str = str(status)

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            paciente_id=paciente_id,
            medico_id=medico_id,
            status=status_str,
            prioridade_clinica=prioridade_int,
            tcle_hash=clean_tcle,
            data_entrada_fila=data_entrada_fila,
            chamada_iniciada_em=chamada_iniciada_em,
            chamada_finalizada_em=chamada_finalizada_em,
        )

    # -------------------------------------------------------------------------
    # Regras e Invariantes do TCLE (RN07, LGPD Art. 11)
    # -------------------------------------------------------------------------

    def registrar_tcle(self, tcle_hash: str) -> None:
        """Registra o hash do TCLE com imutabilidade forense."""
        self._assegurar_nao_finalizado()
        if self.tcle_hash is not None:
            raise ValidationError(
                "TCLE já registrado para este atendimento e não pode ser alterado."
            )
        self.tcle_hash = self._validar_formato_tcle(tcle_hash)
        self.atualizado_em = datetime.now(UTC)

    @staticmethod
    def _validar_formato_tcle(hash_str: str) -> str:
        cleaned = hash_str.strip()
        if not _HEX64_REGEX.match(cleaned):
            raise ValidationError(
                "Hash do TCLE inválido: deve conter 64 caracteres "
                "hexadecimais (SHA-256)."
            )
        return cleaned.lower()

    # -------------------------------------------------------------------------
    # Transições da Máquina de Estados Finita (RN03)
    # -------------------------------------------------------------------------

    def promover_para_apto(self) -> None:
        """Transiciona de TRIADO_AGUARDANDO_ELEGIBILIDADE para APTO_PARA_CHAMADA."""
        self._assegurar_nao_finalizado()
        if self.status != StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos em "
                f"'{StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE}' "
                f"podem ser promovidos para apto. Estado atual: '{self.status}'."
            )

        if self.tcle_hash is None:
            raise ValidationError(
                "Atendimento não pode ser promovido para apto sem consentimento "
                "do TCLE."
            )

        now = datetime.now(UTC)
        self.status = StatusAtendimento.APTO_PARA_CHAMADA.value
        if self.data_entrada_fila is None:
            self.data_entrada_fila = now
        self.atualizado_em = now

    def iniciar_chamada(self, medico_id: UUID) -> None:
        """Aloca o médico e transiciona de APTO_PARA_CHAMADA para CHAMANDO_PACIENTE."""
        self._assegurar_nao_finalizado()
        if not medico_id:
            raise ValidationError(
                "Médico responsável é obrigatório para iniciar a chamada."
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
        """Paciente conecta à videochamada e transiciona para EM_ATENDIMENTO."""
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
        """Timeout de toque (45s sem resposta): transiciona para PACIENTE_AUSENTE."""
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
        """Médico finaliza a teleconsulta e transiciona para CONCLUIDO."""
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
        """Registra desistência do paciente antes da consulta clínica."""
        self._assegurar_nao_finalizado()
        if self.status == StatusAtendimento.EM_ATENDIMENTO:
            raise TransicaoEstadoInvalidaError(
                "Não é possível cancelar atendimento já em andamento clínico."
            )

        if self.status not in (
            StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            StatusAtendimento.APTO_PARA_CHAMADA,
            StatusAtendimento.CHAMANDO_PACIENTE,
        ):
            raise TransicaoEstadoInvalidaError(
                f"Estado '{self.status}' não permite cancelamento pelo paciente."
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
        """Soberania diagnóstica do médico assistente (RN-REG-01)."""
        self._assegurar_nao_finalizado()
        prioridade_int = int(nova_prioridade)
        if prioridade_int < 1 or prioridade_int > 5:
            raise ValidationError(
                "Prioridade clínica deve ser entre 1 e 5 (1=Emergência, 5=Não Urgente)."
            )
        self.prioridade_clinica = prioridade_int
        self.atualizado_em = datetime.now(UTC)

    def calcular_score_fila(self) -> int:
        """Calcula o score de 64 bits para indexação no Sorted Set (ZSET) do Valkey.

        Score = (prioridade_clinica * 10^12) + timestamp_entrada_epoch
        """
        if self.data_entrada_fila is None:
            raise ValidationError(
                "Atendimento sem data de entrada na fila não possui score calculado."
            )
        epoch = int(self.data_entrada_fila.timestamp())
        return (int(self.prioridade_clinica) * 1_000_000_000_000) + epoch

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
