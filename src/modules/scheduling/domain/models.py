"""Modelos ricos e agregados do módulo scheduling (eMulti multiprofissional)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.scheduling.domain.exceptions import TransicaoAgendamentoInvalidaError


class EspecialidadeAgenda(StrEnum):
    """Especialidades suportadas na agenda programada multiprofissional (eMulti)."""

    PSICOLOGIA = "PSICOLOGIA"
    NUTRICAO = "NUTRICAO"


class StatusAgendamento(StrEnum):
    """Estados do ciclo de vida de um agendamento multiprofissional."""

    AGENDADO = "AGENDADO"
    CONFIRMADO = "CONFIRMADO"
    EM_ATENDIMENTO = "EM_ATENDIMENTO"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO = "CANCELADO"
    FALTA = "FALTA"


STATUS_AGENDAMENTO_INATIVOS: frozenset[StatusAgendamento] = frozenset(
    {StatusAgendamento.CANCELADO, StatusAgendamento.FALTA}
)


@dataclass(frozen=True)
class EspecialidadeMetadata:
    """Metadados descritivos de especialidade na agenda eMulti."""

    codigo: EspecialidadeAgenda
    nome: str
    descricao: str
    duracao_padrao_minutos: int


ESPECIALIDADE_CATALOGO: dict[EspecialidadeAgenda, EspecialidadeMetadata] = {
    EspecialidadeAgenda.PSICOLOGIA: EspecialidadeMetadata(
        codigo=EspecialidadeAgenda.PSICOLOGIA,
        nome="Psicologia",
        descricao=(
            "Acompanhamento psicológico clínico multiprofissional programado (eMulti)."
        ),
        duracao_padrao_minutos=50,
    ),
    EspecialidadeAgenda.NUTRICAO: EspecialidadeMetadata(
        codigo=EspecialidadeAgenda.NUTRICAO,
        nome="Nutrição",
        descricao=(
            "Orientação e acompanhamento nutricional clínico programado (eMulti)."
        ),
        duracao_padrao_minutos=30,
    ),
}


def validar_especialidade_agenda(
    valor: EspecialidadeAgenda | str,
) -> EspecialidadeAgenda:
    """Valida e normaliza a especialidade para o enum EspecialidadeAgenda.

    Regras: docs/explanation/domains/scheduling-domain.md
    """
    if isinstance(valor, EspecialidadeAgenda):
        return valor
    normalizado = valor.strip().upper()
    try:
        return EspecialidadeAgenda(normalizado)
    except ValueError as exc:
        esperados = sorted(e.value for e in EspecialidadeAgenda)
        raise ValidationError(
            f"Especialidade '{valor}' inválida; esperadas: {esperados}."
        ) from exc


def normalizar_utc(dt: datetime) -> datetime:
    """Normaliza datetime ingênuo ou com fuso para UTC.

    Regras: docs/explanation/domains/scheduling-domain.md
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _validar_organizacao_id(organizacao_id: int) -> None:
    if organizacao_id <= 0:
        raise ValidationError(
            f"organizacao_id '{organizacao_id}' inválido; "
            "esperado inteiro positivo > 0."
        )


class AgendaDisponibilidade(Base):
    """Janela recorrente de disponibilidade semanal de profissional multiprofissional.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    __tablename__ = "agenda_disponibilidades"
    __table_args__ = (
        CheckConstraint(
            "dia_semana BETWEEN 0 AND 6",
            name="chk_agenda_disp_dia_semana",
        ),
        CheckConstraint(
            "hora_fim > hora_inicio",
            name="chk_agenda_disp_horarios",
        ),
        CheckConstraint(
            "duracao_minutos BETWEEN 15 AND 120",
            name="chk_agenda_disp_duracao",
        ),
        Index(
            "idx_agenda_disp_org_esp",
            "organizacao_id",
            "especialidade",
            "dia_semana",
        ),
        Index("idx_agenda_disp_prof", "organizacao_id", "profissional_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizacoes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profissional_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=False,
    )
    especialidade: Mapped[str] = mapped_column(String(40), nullable=False)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fim: Mapped[time] = mapped_column(Time, nullable=False)
    duracao_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __init__(
        self,
        organizacao_id: int,
        profissional_id: UUID,
        especialidade: EspecialidadeAgenda | str,
        dia_semana: int,
        hora_inicio: time,
        hora_fim: time,
        duracao_minutos: int,
        *,
        ativo: bool = True,
        id: UUID | None = None,
    ) -> None:
        """Inicializa janela semanal validando dia, intervalo e duração de slots.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        _validar_organizacao_id(organizacao_id)
        esp = validar_especialidade_agenda(especialidade)

        if dia_semana < 0 or dia_semana > 6:
            raise ValidationError(
                f"dia_semana '{dia_semana}' inválido; esperado inteiro entre "
                "0 (segunda-feira) e 6 (domingo)."
            )

        if hora_inicio.tzinfo is not None:
            raise ValidationError(
                f"hora_inicio '{hora_inicio.isoformat()}' inválida; "
                "esperado horário sem fuso (naive UTC)."
            )

        if hora_fim.tzinfo is not None:
            raise ValidationError(
                f"hora_fim '{hora_fim.isoformat()}' inválida; "
                "esperado horário sem fuso (naive UTC)."
            )

        if hora_fim <= hora_inicio:
            raise ValidationError(
                f"hora_fim '{hora_fim.isoformat()}' inválida; deve ser "
                f"estritamente posterior a hora_inicio '{hora_inicio.isoformat()}'."
            )

        if duracao_minutos < 15 or duracao_minutos > 120:
            raise ValidationError(
                f"duracao_minutos '{duracao_minutos}' inválida; esperado "
                "valor entre 15 e 120 minutos."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            profissional_id=profissional_id,
            especialidade=esp.value,
            dia_semana=dia_semana,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            duracao_minutos=duracao_minutos,
            ativo=ativo,
        )

    def sobrepoe(self, outra: "AgendaDisponibilidade") -> bool:
        """Indica sobreposição [hora_inicio, hora_fim) no mesmo dia e profissional.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        if not self.ativo or not outra.ativo:
            return False
        if (
            self.organizacao_id != outra.organizacao_id
            or self.profissional_id != outra.profissional_id
            or self.dia_semana != outra.dia_semana
        ):
            return False
        return self.hora_inicio < outra.hora_fim and self.hora_fim > outra.hora_inicio

    def gerar_intervalos(self, dia: date) -> list[tuple[datetime, datetime]]:
        """Gera pares (slot_inicio, slot_fim) UTC da janela para a data informada.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        if not self.ativo or dia.weekday() != self.dia_semana:
            return []
        cursor = datetime.combine(dia, self.hora_inicio, tzinfo=UTC)
        limite = datetime.combine(dia, self.hora_fim, tzinfo=UTC)
        passo = timedelta(minutes=self.duracao_minutos)
        intervalos: list[tuple[datetime, datetime]] = []
        while cursor + passo <= limite:
            proximo = cursor + passo
            intervalos.append((cursor, proximo))
            cursor = proximo
        return intervalos

    def cobre_slot(self, slot_inicio: datetime, slot_fim: datetime) -> bool:
        """Verifica se a janela ativa cobre [slot_inicio, slot_fim] alinhado à grade.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        if not self.ativo:
            return False
        inicio_utc = normalizar_utc(slot_inicio)
        fim_utc = normalizar_utc(slot_fim)
        if fim_utc <= inicio_utc or inicio_utc.weekday() != self.dia_semana:
            return False
        dia = inicio_utc.date()
        janela_inicio = datetime.combine(dia, self.hora_inicio, tzinfo=UTC)
        janela_fim = datetime.combine(dia, self.hora_fim, tzinfo=UTC)
        if inicio_utc < janela_inicio or fim_utc > janela_fim:
            return False
        passo = timedelta(minutes=self.duracao_minutos)
        return (fim_utc - inicio_utc) == passo and (
            (inicio_utc - janela_inicio) % passo == timedelta(0)
        )


class Agendamento(Base):
    """Agregado de agendamento multiprofissional com máquina de estados estrita.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    __tablename__ = "agendamentos"
    __table_args__ = (
        CheckConstraint(
            "slot_fim > slot_inicio",
            name="chk_agendamento_slot_valido",
        ),
        CheckConstraint(
            "status IN ("
            "'AGENDADO', 'CONFIRMADO', 'EM_ATENDIMENTO', "
            "'CONCLUIDO', 'CANCELADO', 'FALTA'"
            ")",
            name="chk_agendamento_status",
        ),
        ExcludeConstraint(
            ("organizacao_id", "="),
            ("profissional_id", "="),
            (
                func.tstzrange(
                    column("slot_inicio"),
                    column("slot_fim"),
                    "[)",
                ),
                "&&",
            ),
            name="excl_agendamento_slot_ativo",
            using="gist",
            where=text("status NOT IN ('CANCELADO', 'FALTA')"),
        ),
        Index(
            "uq_agendamento_slot_ativo",
            "organizacao_id",
            "profissional_id",
            "slot_inicio",
            unique=True,
            postgresql_where=text("status NOT IN ('CANCELADO', 'FALTA')"),
        ),
        Index(
            "uq_agendamento_atendimento_id",
            "atendimento_id",
            unique=True,
            postgresql_where=text("atendimento_id IS NOT NULL"),
        ),
        Index(
            "idx_agendamentos_org_paciente",
            "organizacao_id",
            "paciente_id",
            "slot_inicio",
        ),
        Index(
            "idx_agendamentos_org_profissional",
            "organizacao_id",
            "profissional_id",
            "slot_inicio",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizacoes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    paciente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profissional_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profissionais.id", ondelete="RESTRICT"),
        nullable=False,
    )
    especialidade: Mapped[str] = mapped_column(String(40), nullable=False)
    slot_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    slot_fim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StatusAgendamento.AGENDADO.value
    )
    observacoes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    atendimento_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("atendimentos.id", ondelete="RESTRICT"),
        nullable=True,
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
        profissional_id: UUID,
        especialidade: EspecialidadeAgenda | str,
        slot_inicio: datetime,
        slot_fim: datetime,
        *,
        status: StatusAgendamento | str = StatusAgendamento.AGENDADO,
        observacoes: str | None = None,
        atendimento_id: UUID | None = None,
        criado_em: datetime | None = None,
        atualizado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        """Inicializa agendamento validando tenant, especialidade, slot e status.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        _validar_organizacao_id(organizacao_id)
        esp = validar_especialidade_agenda(especialidade)
        inicio_utc = normalizar_utc(slot_inicio)
        fim_utc = normalizar_utc(slot_fim)

        if fim_utc <= inicio_utc:
            raise ValidationError(
                f"slot_fim '{fim_utc.isoformat()}' inválido; deve ser "
                f"estritamente posterior a slot_inicio '{inicio_utc.isoformat()}'."
            )

        status_enum = self._validar_status_inicial(status)
        obs_limpa = self._validar_observacoes(observacoes)
        agora = datetime.now(UTC)

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            paciente_id=paciente_id,
            profissional_id=profissional_id,
            especialidade=esp.value,
            slot_inicio=inicio_utc,
            slot_fim=fim_utc,
            status=status_enum.value,
            observacoes=obs_limpa,
            atendimento_id=atendimento_id,
            criado_em=criado_em or agora,
            atualizado_em=atualizado_em or agora,
        )

    @staticmethod
    def _validar_status_inicial(
        status: StatusAgendamento | str,
    ) -> StatusAgendamento:
        if isinstance(status, StatusAgendamento):
            return status
        try:
            return StatusAgendamento(status.strip().upper())
        except ValueError as exc:
            esperados = sorted(s.value for s in StatusAgendamento)
            raise ValidationError(
                f"Status de agendamento '{status}' inválido; esperados: {esperados}."
            ) from exc

    @staticmethod
    def _validar_observacoes(observacoes: str | None) -> str | None:
        if observacoes is None:
            return None
        limpa = observacoes.strip()
        if len(limpa) > 500:
            raise ValidationError(
                f"observacoes com {len(limpa)} caracteres excede o limite de 500."
            )
        return limpa or None

    def _transicionar(
        self,
        *,
        destino: StatusAgendamento,
        permitidos: frozenset[StatusAgendamento],
    ) -> None:
        atual = StatusAgendamento(self.status)
        if atual not in permitidos:
            esperados = sorted(s.value for s in permitidos)
            raise TransicaoAgendamentoInvalidaError(
                f"Transição inválida do agendamento '{self.id}' de "
                f"'{atual.value}' para '{destino.value}'; "
                f"estados permitidos: {esperados}."
            )
        self.status = destino.value
        self.atualizado_em = datetime.now(UTC)

    def cancelar(self) -> None:
        """Cancela um agendamento ativo antes do início da consulta.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        self._transicionar(
            destino=StatusAgendamento.CANCELADO,
            permitidos=frozenset(
                {StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO}
            ),
        )

    def iniciar_atendimento(self, atendimento_id: UUID | None = None) -> None:
        """Inicia o atendimento clínico do agendamento, vinculando atendimento opcional.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        self._transicionar(
            destino=StatusAgendamento.EM_ATENDIMENTO,
            permitidos=frozenset(
                {StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO}
            ),
        )
        if atendimento_id is not None:
            self.atendimento_id = atendimento_id
