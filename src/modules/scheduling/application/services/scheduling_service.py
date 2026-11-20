"""Serviço de aplicação para agenda programada multiprofissional (eMulti)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError, ForbiddenError, NotFoundError, ValidationError
from src.modules.scheduling.application.dtos import (
    AgendarConsultaCommand,
    CriarDisponibilidadeCommand,
    SlotDisponivelDTO,
)
from src.modules.scheduling.application.ports.attendance_lookup_port import (
    AttendanceLookupPort,
)
from src.modules.scheduling.application.ports.scheduling_repository_port import (
    SchedulingRepositoryPort,
)
from src.modules.scheduling.domain.exceptions import (
    AgendamentoNaoEncontradoError,
    SlotIndisponivelError,
)
from src.modules.scheduling.domain.models import (
    ESPECIALIDADE_CATALOGO,
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeAgenda,
    EspecialidadeMetadata,
    normalizar_utc,
    validar_especialidade_agenda,
)

_MAX_JANELA_SLOTS_DIAS = 31


def _slot_colide(
    profissional_id: UUID,
    inicio: datetime,
    fim: datetime,
    ocupados: Sequence[Agendamento],
) -> bool:
    return any(
        ag.profissional_id == profissional_id
        and ag.slot_inicio < fim
        and ag.slot_fim > inicio
        for ag in ocupados
    )


def _gerar_slots_janela(
    disp: AgendaDisponibilidade,
    dia: date,
    ocupados: Sequence[Agendamento],
) -> list[SlotDisponivelDTO]:
    gerados: list[SlotDisponivelDTO] = []
    for slot_inicio, slot_fim in disp.gerar_intervalos(dia):
        if _slot_colide(disp.profissional_id, slot_inicio, slot_fim, ocupados):
            continue
        gerados.append(
            SlotDisponivelDTO(
                profissional_id=disp.profissional_id,
                especialidade=disp.especialidade,
                slot_inicio=slot_inicio,
                slot_fim=slot_fim,
                duracao_minutos=disp.duracao_minutos,
            )
        )
    return gerados


def _gerar_slots_no_dia(
    disponibilidades: Sequence[AgendaDisponibilidade],
    dia: date,
    ocupados: Sequence[Agendamento],
) -> list[SlotDisponivelDTO]:
    slots_dia: list[SlotDisponivelDTO] = []
    for disp in disponibilidades:
        slots_dia.extend(_gerar_slots_janela(disp, dia, ocupados))
    return slots_dia


def _validar_intervalo_datas(data_inicio: date, data_fim: date) -> None:
    if data_fim < data_inicio:
        raise ValidationError(
            f"Intervalo inválido: data_fim '{data_fim.isoformat()}' é anterior "
            f"a data_inicio '{data_inicio.isoformat()}'."
        )
    dias = (data_fim - data_inicio).days
    if dias > _MAX_JANELA_SLOTS_DIAS:
        raise ValidationError(
            f"Janela de {dias} dias excede o máximo permitido de "
            f"{_MAX_JANELA_SLOTS_DIAS} dias por consulta."
        )


def _eh_violacao_grade(
    disp: AgendaDisponibilidade,
    dia: date,
    slot_inicio_utc: datetime,
    slot_fim_utc: datetime,
) -> bool:
    janela_ini = datetime.combine(dia, disp.hora_inicio, tzinfo=UTC)
    janela_fim = datetime.combine(dia, disp.hora_fim, tzinfo=UTC)
    if not (janela_ini <= slot_inicio_utc < janela_fim):
        return False
    passo = timedelta(minutes=disp.duracao_minutos)
    desalinhado = (slot_inicio_utc - janela_ini) % passo != timedelta(0)
    duracao_divergente = (slot_fim_utc - slot_inicio_utc) != passo
    return desalinhado or duracao_divergente


def _traduzir_integrity_error_agendamento(
    exc: IntegrityError,
    cmd: AgendarConsultaCommand,
    slot_inicio_utc: datetime,
) -> DomainError:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if sqlstate in {"23505", "23P01"}:
        return SlotIndisponivelError(
            f"Conflito concorrente ao reservar '{slot_inicio_utc.isoformat()}' "
            f"para o profissional '{cmd.profissional_id}' (sqlstate={sqlstate})."
        )
    if sqlstate == "23503":
        return NotFoundError(
            f"Profissional '{cmd.profissional_id}' ou paciente '{cmd.paciente_id}' "
            f"não localizado (constraint='{constraint}')."
        )
    return ValidationError(
        f"Dados inválidos ao persistir agendamento para "
        f"'{slot_inicio_utc.isoformat()}' "
        f"(sqlstate={sqlstate}, constraint='{constraint}')."
    )


class SchedulingService:
    """Orquestra especialidades, geração de slots, reservas e atendimento eMulti.

    Regras: docs/explanation/domains/scheduling-domain.md
    """

    def __init__(
        self,
        session: AsyncSession,
        repository: SchedulingRepositoryPort,
        attendance_lookup: AttendanceLookupPort | None = None,
    ) -> None:
        """Inicializa o serviço com sessão transacional e portas de domínio."""
        self._session = session
        self._repository = repository
        self._attendance_lookup = attendance_lookup

    def listar_especialidades(self) -> list[EspecialidadeMetadata]:
        """Lista as especialidades multiprofissionais disponíveis para agendamento.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        return list(ESPECIALIDADE_CATALOGO.values())

    async def listar_slots_disponiveis(
        self,
        *,
        especialidade: str,
        data_inicio: date,
        data_fim: date,
    ) -> list[SlotDisponivelDTO]:
        """Gera slots livres no período subtraindo agendamentos ativos ocupados.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        esp = validar_especialidade_agenda(especialidade)
        _validar_intervalo_datas(data_inicio, data_fim)

        disponibilidades = await self._repository.listar_disponibilidades_ativas(
            especialidade=esp.value,
        )
        if not disponibilidades:
            return []

        inicio_dt = datetime.combine(data_inicio, datetime.min.time(), tzinfo=UTC)
        fim_dt = datetime.combine(
            data_fim + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        ocupados = await self._repository.listar_agendamentos_ocupados(
            inicio=inicio_dt,
            fim=fim_dt,
        )

        slots: list[SlotDisponivelDTO] = []
        dia_atual = data_inicio
        while dia_atual <= data_fim:
            slots.extend(_gerar_slots_no_dia(disponibilidades, dia_atual, ocupados))
            dia_atual += timedelta(days=1)

        return sorted(slots, key=lambda s: (s.slot_inicio, str(s.profissional_id)))

    async def cadastrar_disponibilidade(
        self,
        cmd: CriarDisponibilidadeCommand,
    ) -> AgendaDisponibilidade:
        """Cadastra janela semanal recorrente para o profissional autenticado.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        disponibilidade = AgendaDisponibilidade(
            profissional_id=cmd.profissional_id,
            especialidade=cmd.especialidade,
            dia_semana=cmd.dia_semana,
            hora_inicio=cmd.hora_inicio,
            hora_fim=cmd.hora_fim,
            duracao_minutos=cmd.duracao_minutos,
        )
        existentes = await self._repository.buscar_disponibilidade_profissional(
            profissional_id=cmd.profissional_id,
            especialidade=None,
            dia_semana=cmd.dia_semana,
        )
        for existente in existentes:
            if existente.sobrepoe(disponibilidade):
                inicio_iso = cmd.hora_inicio.isoformat()
                fim_iso = cmd.hora_fim.isoformat()
                raise SlotIndisponivelError(
                    f"Janela [{inicio_iso}, {fim_iso}) "
                    f"sobrepõe disponibilidade '{existente.id}' "
                    f"[{existente.hora_inicio.isoformat()}, "
                    f"{existente.hora_fim.isoformat()}) para o profissional "
                    f"'{cmd.profissional_id}' no dia {cmd.dia_semana}."
                )

        self._repository.adicionar_disponibilidade(disponibilidade)
        await self._session.commit()
        return disponibilidade

    async def _validar_e_resolver_slot(
        self,
        cmd: AgendarConsultaCommand,
        esp: EspecialidadeAgenda,
        slot_inicio_utc: datetime,
    ) -> datetime:
        disponibilidades = await self._repository.buscar_disponibilidade_profissional(
            profissional_id=cmd.profissional_id,
            especialidade=esp.value,
            dia_semana=slot_inicio_utc.weekday(),
        )
        if not disponibilidades:
            raise SlotIndisponivelError(
                f"Profissional '{cmd.profissional_id}' sem agenda ativa em "
                f"'{esp.value}' para o dia da semana {slot_inicio_utc.weekday()}."
            )

        slot_fim_explicito = (
            normalizar_utc(cmd.slot_fim) if cmd.slot_fim is not None else None
        )
        if slot_fim_explicito is not None and slot_fim_explicito <= slot_inicio_utc:
            raise ValidationError(
                f"slot_fim '{slot_fim_explicito.isoformat()}' inválido; deve ser "
                f"estritamente posterior a slot_inicio '{slot_inicio_utc.isoformat()}'."
            )

        return self._casar_disponibilidade(
            disponibilidades=disponibilidades,
            profissional_id=cmd.profissional_id,
            especialidade=esp,
            slot_inicio_utc=slot_inicio_utc,
            slot_fim_explicito=slot_fim_explicito,
        )

    @staticmethod
    def _casar_disponibilidade(
        *,
        disponibilidades: Sequence[AgendaDisponibilidade],
        profissional_id: UUID,
        especialidade: EspecialidadeAgenda,
        slot_inicio_utc: datetime,
        slot_fim_explicito: datetime | None,
    ) -> datetime:
        dia = slot_inicio_utc.date()
        violacao_grade = False
        for disp in disponibilidades:
            slot_fim_esperado = slot_inicio_utc + timedelta(
                minutes=disp.duracao_minutos
            )
            slot_fim = (
                slot_fim_explicito
                if slot_fim_explicito is not None
                else slot_fim_esperado
            )
            if disp.cobre_slot(slot_inicio_utc, slot_fim):
                return slot_fim
            if _eh_violacao_grade(disp, dia, slot_inicio_utc, slot_fim):
                violacao_grade = True

        if violacao_grade:
            duracoes = sorted({d.duracao_minutos for d in disponibilidades})
            fim_desc = slot_fim_explicito.isoformat() if slot_fim_explicito else "auto"
            raise ValidationError(
                f"Slot [{slot_inicio_utc.isoformat()}, {fim_desc}) diverge da "
                f"grade ou duração permitida {duracoes} min da agenda do "
                f"profissional '{profissional_id}'."
            )
        raise SlotIndisponivelError(
            f"Horário '{slot_inicio_utc.isoformat()}' indisponível na agenda de "
            f"'{especialidade.value}' do profissional '{profissional_id}'."
        )

    async def agendar_consulta(
        self,
        cmd: AgendarConsultaCommand,
    ) -> Agendamento:
        """Agenda consulta para o paciente autenticado prevenindo double-booking.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        esp = validar_especialidade_agenda(cmd.especialidade)
        slot_inicio_utc = normalizar_utc(cmd.slot_inicio)
        agora = datetime.now(UTC)
        if slot_inicio_utc < agora:
            raise ValidationError(
                f"slot_inicio '{slot_inicio_utc.isoformat()}' inválido; não é "
                f"permitido agendar horário no passado (atual: '{agora.isoformat()}')."
            )

        slot_fim_utc = await self._validar_e_resolver_slot(cmd, esp, slot_inicio_utc)

        conflito = await self._repository.buscar_agendamento_conflitante(
            profissional_id=cmd.profissional_id,
            slot_inicio=slot_inicio_utc,
            slot_fim=slot_fim_utc,
        )
        if conflito is not None:
            raise SlotIndisponivelError(
                f"Horário '{slot_inicio_utc.isoformat()}' já ocupado para o "
                f"profissional '{cmd.profissional_id}'."
            )

        agendamento = Agendamento(
            paciente_id=cmd.paciente_id,
            profissional_id=cmd.profissional_id,
            especialidade=esp,
            slot_inicio=slot_inicio_utc,
            slot_fim=slot_fim_utc,
            observacoes=cmd.observacoes,
        )
        self._repository.adicionar_agendamento(agendamento)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _traduzir_integrity_error_agendamento(
                exc, cmd, slot_inicio_utc
            ) from exc

        return agendamento

    async def listar_agendamentos_paciente(
        self,
        *,
        paciente_id: UUID,
    ) -> list[Agendamento]:
        """Lista agendamentos pertencentes exclusivamente ao paciente autenticado.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        itens = await self._repository.listar_agendamentos_paciente(
            paciente_id=paciente_id,
        )
        return list(itens)

    async def cancelar_agendamento(
        self,
        *,
        agendamento_id: UUID,
        paciente_id: UUID,
    ) -> Agendamento:
        """Cancela agendamento somente se pertencer ao paciente solicitante.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        agendamento = await self._repository.buscar_agendamento_por_id(
            agendamento_id=agendamento_id,
            for_update=True,
        )
        if agendamento is None:
            raise AgendamentoNaoEncontradoError(
                f"Agendamento '{agendamento_id}' não encontrado."
            )
        if agendamento.paciente_id != paciente_id:
            raise ForbiddenError(
                f"Acesso negado: agendamento '{agendamento_id}' não pertence ao "
                f"paciente '{paciente_id}'."
            )

        agendamento.cancelar()
        await self._session.commit()
        return agendamento

    async def listar_agenda_profissional(
        self,
        *,
        profissional_id: UUID,
        data_inicio: date,
        data_fim: date,
    ) -> list[Agendamento]:
        """Lista os agendamentos do profissional autenticado no período solicitado.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        _validar_intervalo_datas(data_inicio, data_fim)
        inicio_dt = datetime.combine(data_inicio, datetime.min.time(), tzinfo=UTC)
        fim_dt = datetime.combine(
            data_fim + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        itens = await self._repository.listar_agendamentos_profissional(
            profissional_id=profissional_id,
            inicio=inicio_dt,
            fim=fim_dt,
        )
        return list(itens)

    async def _validar_atendimento_vinculado(
        self,
        *,
        atendimento_id: UUID,
        agendamento: Agendamento,
        profissional_id: UUID,
    ) -> None:
        if self._attendance_lookup is None:
            raise RuntimeError(
                "AttendanceLookupPort não configurado em SchedulingService para "
                f"validar o atendimento '{atendimento_id}'."
            )
        atendimento = await self._attendance_lookup.buscar_atendimento(atendimento_id)
        if atendimento is None:
            raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")
        if atendimento.paciente_id != agendamento.paciente_id:
            raise ValidationError(
                f"Atendimento '{atendimento_id}' pertence ao paciente "
                f"'{atendimento.paciente_id}', divergente do paciente "
                f"'{agendamento.paciente_id}' do agendamento '{agendamento.id}'."
            )
        if (
            atendimento.medico_id is not None
            and atendimento.medico_id != profissional_id
        ):
            raise ForbiddenError(
                f"Acesso negado: atendimento '{atendimento_id}' já alocado ao "
                f"profissional '{atendimento.medico_id}', divergente de "
                f"'{profissional_id}'."
            )

    async def iniciar_atendimento_agendado(
        self,
        *,
        agendamento_id: UUID,
        profissional_id: UUID,
        atendimento_id: UUID | None = None,
    ) -> Agendamento:
        """Transiciona agendamento do profissional para EM_ATENDIMENTO.

        Regras: docs/explanation/domains/scheduling-domain.md
        """
        agendamento = await self._repository.buscar_agendamento_por_id(
            agendamento_id=agendamento_id,
            for_update=True,
        )
        if agendamento is None:
            raise AgendamentoNaoEncontradoError(
                f"Agendamento '{agendamento_id}' não encontrado."
            )
        if agendamento.profissional_id != profissional_id:
            raise ForbiddenError(
                f"Acesso negado: agendamento '{agendamento_id}' pertence a outro "
                f"profissional (solicitante: '{profissional_id}')."
            )
        if atendimento_id is not None:
            await self._validar_atendimento_vinculado(
                atendimento_id=atendimento_id,
                agendamento=agendamento,
                profissional_id=profissional_id,
            )

        agendamento.iniciar_atendimento(atendimento_id=atendimento_id)
        await self._session.commit()
        return agendamento
