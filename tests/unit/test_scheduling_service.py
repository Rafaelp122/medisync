"""Testes unitários para serviços e repositório do módulo scheduling."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from src.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from src.modules.scheduling.application.dtos import (
    AgendarConsultaCommand,
    CriarDisponibilidadeCommand,
)
from src.modules.scheduling.application.ports.attendance_lookup_port import (
    AttendanceSnapshot,
)
from src.modules.scheduling.application.services.scheduling_service import (
    SchedulingService,
)
from src.modules.scheduling.domain.exceptions import (
    AgendamentoNaoEncontradoError,
    SlotIndisponivelError,
    TransicaoAgendamentoInvalidaError,
)
from src.modules.scheduling.domain.models import (
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeAgenda,
    EspecialidadeMetadata,
    StatusAgendamento,
)
from src.modules.scheduling.infrastructure.adapters.sql_scheduling_repository import (
    SqlSchedulingRepository,
)

from tests.doubles import (
    FakeAsyncSession,
    FakeAttendanceLookup,
    FakeResult,
    FakeSchedulingRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _dia_futuro(dias_a_frente: int = 7) -> date:
    return (datetime.now(UTC) + timedelta(days=dias_a_frente)).date()


def _build_service() -> tuple[
    SchedulingService,
    FakeAsyncSession,
    FakeSchedulingRepository,
    FakeAttendanceLookup,
]:
    session = FakeAsyncSession()
    repo = FakeSchedulingRepository()
    lookup = FakeAttendanceLookup()
    return (
        SchedulingService(
            session=cast("AsyncSession", session),
            repository=repo,
            attendance_lookup=lookup,
        ),
        session,
        repo,
        lookup,
    )


async def _registrar_janela(
    service: SchedulingService,
    *,
    prof_id: UUID,
    dia: date,
    especialidade: str = "PSICOLOGIA",
    hora_inicio: time = time(8, 0),
    hora_fim: time = time(18, 0),
    duracao_minutos: int = 50,
) -> AgendaDisponibilidade:
    return await service.cadastrar_disponibilidade(
        CriarDisponibilidadeCommand(
            profissional_id=prof_id,
            especialidade=especialidade,
            dia_semana=dia.weekday(),
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            duracao_minutos=duracao_minutos,
        )
    )


@pytest.mark.asyncio
async def test_listar_especialidades_retorna_metadata_direta() -> None:
    service, _, _, _ = _build_service()
    especialidades = service.listar_especialidades()
    assert all(isinstance(e, EspecialidadeMetadata) for e in especialidades)
    codigos = {e.codigo for e in especialidades}
    assert codigos == {EspecialidadeAgenda.PSICOLOGIA, EspecialidadeAgenda.NUTRICAO}
    mapa = {e.codigo: e for e in especialidades}
    assert mapa[EspecialidadeAgenda.PSICOLOGIA].duracao_padrao_minutos == 50
    assert mapa[EspecialidadeAgenda.NUTRICAO].duracao_padrao_minutos == 30


@pytest.mark.asyncio
async def test_geracao_slots_subtrai_agendamentos_ocupados_todas_especialidades() -> (
    None
):
    service, session, repo, _ = _build_service()
    prof_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="NUTRICAO",
        hora_inicio=time(9, 0),
        hora_fim=time(10, 30),
        duracao_minutos=30,
    )
    assert session.commits == 1

    # Ocupa o slot das 09:30 às 10:00 em OUTRA especialidade (deve bloquear!)
    repo.adicionar_agendamento(
        Agendamento(
            paciente_id=uuid4(),
            profissional_id=prof_id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            slot_inicio=datetime.combine(dia, time(9, 30), tzinfo=UTC),
            slot_fim=datetime.combine(dia, time(10, 0), tzinfo=UTC),
        )
    )
    # Slot cancelado NÃO deve bloquear horário das 10:00
    repo.adicionar_agendamento(
        Agendamento(
            paciente_id=uuid4(),
            profissional_id=prof_id,
            especialidade=EspecialidadeAgenda.NUTRICAO,
            slot_inicio=datetime.combine(dia, time(10, 0), tzinfo=UTC),
            slot_fim=datetime.combine(dia, time(10, 30), tzinfo=UTC),
            status=StatusAgendamento.CANCELADO,
        )
    )

    slots = await service.listar_slots_disponiveis(
        especialidade="NUTRICAO",
        data_inicio=dia,
        data_fim=dia,
    )
    inicios = [s.slot_inicio for s in slots]
    assert inicios == [
        datetime.combine(dia, time(9, 0), tzinfo=UTC),
        datetime.combine(dia, time(10, 0), tzinfo=UTC),
    ]


@pytest.mark.asyncio
async def test_cadastrar_disponibilidade_rejeita_sobreposicao_e_aceita_adjacente() -> (
    None
):
    service, _, _, _ = _build_service()
    prof_id = uuid4()
    dia = _dia_futuro(7)

    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(8, 0),
        hora_fim=time(10, 0),
        duracao_minutos=50,
    )

    # Sobreposição parcial (mesmo dia e profissional, outra especialidade) -> 409
    with pytest.raises(SlotIndisponivelError, match="sobrepõe"):
        await _registrar_janela(
            service,
            prof_id=prof_id,
            dia=dia,
            especialidade="NUTRICAO",
            hora_inicio=time(9, 30),
            hora_fim=time(11, 30),
            duracao_minutos=30,
        )

    # Adjacente [10:00, 12:00) NÃO sobrepõe -> 201 OK
    adjacente = await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="NUTRICAO",
        hora_inicio=time(10, 0),
        hora_fim=time(12, 0),
        duracao_minutos=30,
    )
    assert adjacente.hora_inicio == time(10, 0)


@pytest.mark.asyncio
async def test_listar_slots_rejeita_intervalo_invalido() -> None:
    service, _, _, _ = _build_service()
    with pytest.raises(ValidationError):
        await service.listar_slots_disponiveis(
            especialidade="PSICOLOGIA",
            data_inicio=date(2026, 11, 20),
            data_fim=date(2026, 11, 18),
        )


@pytest.mark.asyncio
async def test_agendar_consulta_previne_conflito_double_booking() -> None:
    service, session, _, _ = _build_service()
    prof_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(13, 0),
        hora_fim=time(16, 0),
        duracao_minutos=50,
    )
    inicio = datetime.combine(dia, time(13, 50), tzinfo=UTC)
    fim = inicio + timedelta(minutes=50)

    primeiro = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=uuid4(),
            profissional_id=prof_id,
            especialidade="PSICOLOGIA",
            slot_inicio=inicio,
            slot_fim=fim,
        )
    )
    assert primeiro.status == StatusAgendamento.AGENDADO.value
    assert session.commits == 2

    with pytest.raises(ConflictError) as exc_info:
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=inicio,
                slot_fim=fim,
            )
        )
    assert isinstance(exc_info.value, SlotIndisponivelError)


@pytest.mark.asyncio
async def test_agendar_consulta_rejeita_passado_sem_agenda_ou_fora_da_grade() -> None:
    service, _, _, _ = _build_service()
    prof_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )

    # 1. Data no passado -> ValidationError
    passado = datetime.now(UTC) - timedelta(hours=1)
    with pytest.raises(ValidationError, match="passado"):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=passado,
            )
        )

    # 2. Profissional sem agenda ativa nessa especialidade/dia -> SlotIndisponivelError
    with pytest.raises(SlotIndisponivelError):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="NUTRICAO",
                slot_inicio=datetime.combine(dia, time(8, 0), tzinfo=UTC),
            )
        )

    # 3. Horário fora da janela ativa -> SlotIndisponivelError
    with pytest.raises(SlotIndisponivelError):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=datetime.combine(dia, time(14, 0), tzinfo=UTC),
            )
        )

    # 4. slot_inicio desalinhado da grade (08:15) -> ValidationError
    with pytest.raises(ValidationError):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=datetime.combine(dia, time(8, 15), tzinfo=UTC),
            )
        )

    # 5. slot_fim divergente da duracao_minutos (30m em vez de 50m) -> ValidationError
    with pytest.raises(ValidationError):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=datetime.combine(dia, time(8, 0), tzinfo=UTC),
                slot_fim=datetime.combine(dia, time(8, 30), tzinfo=UTC),
            )
        )


@pytest.mark.asyncio
async def test_cancelar_agendamento_anti_idor_e_for_update() -> None:
    service, _, repo, _ = _build_service()
    dono_id = uuid4()
    invasor_id = uuid4()
    prof_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="NUTRICAO",
        hora_inicio=time(14, 0),
        hora_fim=time(17, 0),
        duracao_minutos=30,
    )
    inicio = datetime.combine(dia, time(15, 0), tzinfo=UTC)

    ag = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=dono_id,
            profissional_id=prof_id,
            especialidade="NUTRICAO",
            slot_inicio=inicio,
        )
    )

    with pytest.raises(ForbiddenError):
        await service.cancelar_agendamento(
            agendamento_id=ag.id,
            paciente_id=invasor_id,
        )
    assert repo.last_for_update is True

    cancelado = await service.cancelar_agendamento(
        agendamento_id=ag.id,
        paciente_id=dono_id,
    )
    assert repo.last_for_update is True
    assert cancelado.status == StatusAgendamento.CANCELADO.value


@pytest.mark.asyncio
async def test_iniciar_atendimento_agendado_valida_profissional_e_lookup() -> None:
    service, _, repo, lookup = _build_service()
    prof_id = uuid4()
    outro_prof = uuid4()
    paciente_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(14, 0),
        hora_fim=time(18, 0),
        duracao_minutos=50,
    )
    inicio = datetime.combine(dia, time(14, 50), tzinfo=UTC)

    ag = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=prof_id,
            especialidade="PSICOLOGIA",
            slot_inicio=inicio,
        )
    )

    with pytest.raises(ForbiddenError):
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=outro_prof,
        )
    assert repo.last_for_update is True

    # Atendimento inexistente -> 404 NotFoundError
    with pytest.raises(NotFoundError):
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=prof_id,
            atendimento_id=uuid4(),
        )

    # Atendimento de outro paciente -> 422 ValidationError
    atend_outro_pac = uuid4()
    lookup.atendimentos[atend_outro_pac] = AttendanceSnapshot(
        id=atend_outro_pac,
        paciente_id=uuid4(),
        medico_id=prof_id,
    )
    with pytest.raises(ValidationError):
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=prof_id,
            atendimento_id=atend_outro_pac,
        )

    # Atendimento já alocado a outro médico -> 403 ForbiddenError
    atend_outro_med = uuid4()
    lookup.atendimentos[atend_outro_med] = AttendanceSnapshot(
        id=atend_outro_med,
        paciente_id=paciente_id,
        medico_id=outro_prof,
    )
    with pytest.raises(ForbiddenError):
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=prof_id,
            atendimento_id=atend_outro_med,
        )

    # Atendimento válido (mesmo paciente, medico_id compatível) -> 200 OK
    atendimento_id = uuid4()
    lookup.atendimentos[atendimento_id] = AttendanceSnapshot(
        id=atendimento_id,
        paciente_id=paciente_id,
        medico_id=prof_id,
    )
    iniciado = await service.iniciar_atendimento_agendado(
        agendamento_id=ag.id,
        profissional_id=prof_id,
        atendimento_id=atendimento_id,
    )
    assert repo.last_for_update is True
    assert iniciado.status == StatusAgendamento.EM_ATENDIMENTO.value
    assert iniciado.atendimento_id == atendimento_id


@pytest.mark.asyncio
async def test_cancelar_agendamento_inexistente_lanca_404() -> None:
    service, _, _, _ = _build_service()
    with pytest.raises(AgendamentoNaoEncontradoError):
        await service.cancelar_agendamento(
            agendamento_id=uuid4(),
            paciente_id=uuid4(),
        )


class _IntegrityErrorCommitSession(FakeAsyncSession):
    """FakeAsyncSession that raises IntegrityError on commit and tracks rollback."""

    def __init__(
        self,
        *,
        sqlstate: str | None,
        constraint_name: str = "constr_teste",
    ) -> None:
        super().__init__()
        self._sqlstate = sqlstate
        self._constraint_name = constraint_name
        self.rolled_back = False

    async def commit(self) -> None:
        orig = cast(
            "Any",
            SimpleNamespace(
                sqlstate=self._sqlstate,
                diag=SimpleNamespace(constraint_name=self._constraint_name),
            ),
        )
        raise IntegrityError("INSERT/UPDATE", {}, orig)

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sqlstate", "expected_exc"),
    [
        ("23505", SlotIndisponivelError),
        ("23P01", SlotIndisponivelError),
        ("23503", NotFoundError),
        ("23514", ValidationError),
        (None, ValidationError),
    ],
)
async def test_agendar_consulta_integrity_error_classifica_por_sqlstate(
    sqlstate: str | None,
    expected_exc: type[Exception],
) -> None:
    session = _IntegrityErrorCommitSession(sqlstate=sqlstate)
    repo = FakeSchedulingRepository()
    lookup = FakeAttendanceLookup()
    service = SchedulingService(
        session=cast("AsyncSession", session),
        repository=repo,
        attendance_lookup=lookup,
    )
    prof_id = uuid4()
    dia = _dia_futuro(7)
    repo.adicionar_disponibilidade(
        AgendaDisponibilidade(
            profissional_id=prof_id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=dia.weekday(),
            hora_inicio=time(16, 0),
            hora_fim=time(19, 0),
            duracao_minutos=50,
        )
    )

    with pytest.raises(expected_exc):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=uuid4(),
                profissional_id=prof_id,
                especialidade="PSICOLOGIA",
                slot_inicio=datetime.combine(dia, time(16, 0), tzinfo=UTC),
            )
        )
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_listar_agendamentos_paciente_e_agenda_profissional() -> None:
    service, _, _, _ = _build_service()
    pac_1 = uuid4()
    pac_2 = uuid4()
    prof_1 = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_1,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(9, 0),
        hora_fim=time(13, 0),
        duracao_minutos=50,
    )

    await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=pac_1,
            profissional_id=prof_1,
            especialidade="PSICOLOGIA",
            slot_inicio=datetime.combine(dia, time(9, 50), tzinfo=UTC),
        )
    )
    await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=pac_2,
            profissional_id=prof_1,
            especialidade="PSICOLOGIA",
            slot_inicio=datetime.combine(dia, time(10, 40), tzinfo=UTC),
        )
    )

    meus = await service.listar_agendamentos_paciente(paciente_id=pac_1)
    assert len(meus) == 1
    assert meus[0].paciente_id == pac_1

    agenda = await service.listar_agenda_profissional(
        profissional_id=prof_1,
        data_inicio=dia,
        data_fim=dia,
    )
    assert len(agenda) == 2


@pytest.mark.asyncio
async def test_sql_scheduling_repository_com_fake_async_session() -> None:
    from src.modules.scheduling.composition import build_scheduling_service

    ag = Agendamento(
        paciente_id=uuid4(),
        profissional_id=uuid4(),
        especialidade=EspecialidadeAgenda.NUTRICAO,
        slot_inicio=datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
        slot_fim=datetime(2026, 11, 20, 8, 30, tzinfo=UTC),
    )
    session = FakeAsyncSession(results=[FakeResult([ag])])
    service = build_scheduling_service(session=cast("AsyncSession", session))
    itens = await service.listar_agendamentos_paciente(paciente_id=ag.paciente_id)
    assert len(itens) == 1
    assert itens[0].id == ag.id


@pytest.mark.asyncio
async def test_sql_scheduling_repository_for_update_e_sem_especialidade() -> None:
    captured_stmts: list[Any] = []

    class InspectingSession(FakeAsyncSession):
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            if args:
                captured_stmts.append(args[0])
            return await super().execute(*args, **kwargs)

    session = InspectingSession(results=[FakeResult(None), FakeResult([])])
    repo = SqlSchedulingRepository(session=cast("AsyncSession", session))

    await repo.buscar_agendamento_por_id(uuid4(), for_update=True)
    stmt_for_update = str(
        captured_stmts[0].compile(dialect=postgresql.dialect())
    ).upper()
    assert "FOR UPDATE" in stmt_for_update

    prof_id = uuid4()
    ocupados_vazio = await repo.listar_agendamentos_ocupados(
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        profissional_ids=[],
    )
    assert ocupados_vazio == []
    assert len(captured_stmts) == 1

    await repo.listar_agendamentos_ocupados(
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        profissional_ids=[prof_id, prof_id],
    )
    stmt_ocupados = str(captured_stmts[1].compile(dialect=postgresql.dialect()))
    where_clause = stmt_ocupados.split("WHERE", 1)[1]
    assert "agendamentos.especialidade" not in where_clause
    assert "agendamentos.profissional_id IN" in where_clause


def test_scheduling_service_exige_attendance_lookup_obrigatorio() -> None:
    import inspect

    param = inspect.signature(SchedulingService.__init__).parameters[
        "attendance_lookup"
    ]
    assert param.default is inspect.Parameter.empty

    kwargs: dict[str, Any] = {
        "session": cast("AsyncSession", FakeAsyncSession()),
        "repository": FakeSchedulingRepository(),
    }
    with pytest.raises(TypeError, match="attendance_lookup"):
        SchedulingService(**kwargs)


@pytest.mark.asyncio
async def test_listar_slots_filtra_passado_e_repassa_profissional_ids() -> None:
    service, _, repo, _ = _build_service()
    prof_psi_ativo = uuid4()
    prof_psi_inativo = uuid4()
    prof_nutri = uuid4()
    agora_inicio = datetime.now(UTC)
    ontem = (agora_inicio - timedelta(days=1)).date()
    hoje = agora_inicio.date()
    amanha = (agora_inicio + timedelta(days=1)).date()

    for dia in (ontem, hoje, amanha):
        await _registrar_janela(
            service,
            prof_id=prof_psi_ativo,
            dia=dia,
            especialidade="PSICOLOGIA",
            hora_inicio=time(0, 0),
            hora_fim=time(23, 50),
            duracao_minutos=50,
        )
    repo.adicionar_disponibilidade(
        AgendaDisponibilidade(
            profissional_id=prof_psi_inativo,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=amanha.weekday(),
            hora_inicio=time(8, 0),
            hora_fim=time(12, 0),
            duracao_minutos=50,
            ativo=False,
        )
    )
    await _registrar_janela(
        service,
        prof_id=prof_nutri,
        dia=amanha,
        especialidade="NUTRICAO",
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=30,
    )

    slots_passado = await service.listar_slots_disponiveis(
        especialidade="PSICOLOGIA",
        data_inicio=ontem,
        data_fim=ontem,
    )
    assert slots_passado == []
    assert repo.last_ocupados_profissional_ids == {prof_psi_ativo}

    slots_futuros = await service.listar_slots_disponiveis(
        especialidade="PSICOLOGIA",
        data_inicio=hoje,
        data_fim=amanha,
    )
    assert slots_futuros
    assert all(slot.slot_inicio >= agora_inicio for slot in slots_futuros)
    assert repo.last_ocupados_profissional_ids == {prof_psi_ativo}


@pytest.mark.asyncio
async def test_cadastrar_disponibilidade_adquire_lock_e_traduz_concorrencia() -> None:
    service, _, repo, _ = _build_service()
    prof_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )
    assert repo.lock_calls == [(prof_id, dia.weekday())]

    session_err = _IntegrityErrorCommitSession(
        sqlstate="23P01",
        constraint_name="excl_agenda_disp_sobreposicao",
    )
    repo_err = FakeSchedulingRepository()
    service_err = SchedulingService(
        session=cast("AsyncSession", session_err),
        repository=repo_err,
        attendance_lookup=FakeAttendanceLookup(),
    )
    with pytest.raises(SlotIndisponivelError, match="23P01"):
        await _registrar_janela(
            service_err,
            prof_id=prof_id,
            dia=dia,
            especialidade="NUTRICAO",
            hora_inicio=time(13, 0),
            hora_fim=time(15, 0),
            duracao_minutos=30,
        )
    assert session_err.rolled_back is True
    assert repo_err.lock_calls == [(prof_id, dia.weekday())]


@pytest.mark.asyncio
async def test_agendar_consulta_bloqueia_double_booking_paciente() -> None:
    service, _, _, _ = _build_service()
    paciente_id = uuid4()
    prof_psi = uuid4()
    prof_nutri = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_psi,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(9, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )
    await _registrar_janela(
        service,
        prof_id=prof_nutri,
        dia=dia,
        especialidade="NUTRICAO",
        hora_inicio=time(9, 0),
        hora_fim=time(12, 0),
        duracao_minutos=30,
    )

    ag_psi = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=prof_psi,
            especialidade="PSICOLOGIA",
            slot_inicio=datetime.combine(dia, time(9, 0), tzinfo=UTC),
        )
    )

    with pytest.raises(SlotIndisponivelError, match=str(paciente_id)):
        await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=paciente_id,
                profissional_id=prof_nutri,
                especialidade="NUTRICAO",
                slot_inicio=datetime.combine(dia, time(9, 30), tzinfo=UTC),
            )
        )

    await service.marcar_falta_agendamento(
        agendamento_id=ag_psi.id,
        profissional_id=prof_psi,
    )
    ag_nutri = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=prof_nutri,
            especialidade="NUTRICAO",
            slot_inicio=datetime.combine(dia, time(9, 30), tzinfo=UTC),
        )
    )
    assert ag_nutri.profissional_id == prof_nutri

    # Corrida de banco na constraint excl_agendamento_paciente_ativo -> 409 paciente
    session_err = _IntegrityErrorCommitSession(
        sqlstate="23P01",
        constraint_name="excl_agendamento_paciente_ativo",
    )
    repo_err = FakeSchedulingRepository()
    repo_err.adicionar_disponibilidade(
        AgendaDisponibilidade(
            profissional_id=prof_nutri,
            especialidade=EspecialidadeAgenda.NUTRICAO,
            dia_semana=dia.weekday(),
            hora_inicio=time(9, 0),
            hora_fim=time(12, 0),
            duracao_minutos=30,
        )
    )
    service_err = SchedulingService(
        session=cast("AsyncSession", session_err),
        repository=repo_err,
        attendance_lookup=FakeAttendanceLookup(),
    )
    with pytest.raises(
        SlotIndisponivelError, match="excl_agendamento_paciente_ativo"
    ) as exc_race:
        await service_err.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=paciente_id,
                profissional_id=prof_nutri,
                especialidade="NUTRICAO",
                slot_inicio=datetime.combine(dia, time(9, 30), tzinfo=UTC),
            )
        )
    assert str(paciente_id) in str(exc_race.value)
    assert session_err.rolled_back is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sqlstate", "expected_exc"),
    [
        ("23505", ConflictError),
        ("23P01", ConflictError),
        ("23503", NotFoundError),
        ("23514", ValidationError),
    ],
)
async def test_iniciar_atendimento_agendado_integrity_error_retorna_erro_com_ids(
    sqlstate: str,
    expected_exc: type[Exception],
) -> None:
    session = _IntegrityErrorCommitSession(
        sqlstate=sqlstate,
        constraint_name="uq_agendamento_atendimento_id",
    )
    repo = FakeSchedulingRepository()
    lookup = FakeAttendanceLookup()
    prof_id = uuid4()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    dia = _dia_futuro(7)
    ag = Agendamento(
        paciente_id=paciente_id,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        slot_inicio=datetime.combine(dia, time(10, 0), tzinfo=UTC),
        slot_fim=datetime.combine(dia, time(10, 50), tzinfo=UTC),
    )
    repo.adicionar_agendamento(ag)
    lookup.atendimentos[atendimento_id] = AttendanceSnapshot(
        id=atendimento_id,
        paciente_id=paciente_id,
        medico_id=prof_id,
    )
    service = SchedulingService(
        session=cast("AsyncSession", session),
        repository=repo,
        attendance_lookup=lookup,
    )

    with pytest.raises(expected_exc) as exc_info:
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=prof_id,
            atendimento_id=atendimento_id,
        )
    assert session.rolled_back is True
    assert str(ag.id) in str(exc_info.value)
    assert str(atendimento_id) in str(exc_info.value)


@pytest.mark.asyncio
async def test_concluir_e_marcar_falta_agendamento_ciclo_de_vida_e_anti_idor() -> None:
    service, session, repo, _ = _build_service()
    prof_id = uuid4()
    outro_prof = uuid4()
    paciente_id = uuid4()
    dia = _dia_futuro(7)
    await _registrar_janela(
        service,
        prof_id=prof_id,
        dia=dia,
        especialidade="PSICOLOGIA",
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )

    ag_concluir = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=prof_id,
            especialidade="PSICOLOGIA",
            slot_inicio=datetime.combine(dia, time(8, 0), tzinfo=UTC),
        )
    )
    # Concluir antes de iniciar -> 409 TransicaoAgendamentoInvalidaError
    with pytest.raises(TransicaoAgendamentoInvalidaError, match="AGENDADO"):
        await service.concluir_agendamento(
            agendamento_id=ag_concluir.id,
            profissional_id=prof_id,
        )

    await service.iniciar_atendimento_agendado(
        agendamento_id=ag_concluir.id,
        profissional_id=prof_id,
    )
    with pytest.raises(ForbiddenError):
        await service.concluir_agendamento(
            agendamento_id=ag_concluir.id,
            profissional_id=outro_prof,
        )

    commits_antes = session.commits
    concluido = await service.concluir_agendamento(
        agendamento_id=ag_concluir.id,
        profissional_id=prof_id,
    )
    assert repo.last_for_update is True
    assert session.commits == commits_antes + 1
    assert concluido.status == StatusAgendamento.CONCLUIDO.value

    # Marcar falta em estado terminal CONCLUIDO -> 409
    with pytest.raises(TransicaoAgendamentoInvalidaError, match="CONCLUIDO"):
        await service.marcar_falta_agendamento(
            agendamento_id=ag_concluir.id,
            profissional_id=prof_id,
        )

    # Marcar falta em AGENDADO -> FALTA e libera slot
    ag_falta = await service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=uuid4(),
            profissional_id=prof_id,
            especialidade="PSICOLOGIA",
            slot_inicio=datetime.combine(dia, time(8, 50), tzinfo=UTC),
        )
    )
    with pytest.raises(ForbiddenError):
        await service.marcar_falta_agendamento(
            agendamento_id=ag_falta.id,
            profissional_id=outro_prof,
        )
    faltoso = await service.marcar_falta_agendamento(
        agendamento_id=ag_falta.id,
        profissional_id=prof_id,
    )
    assert repo.last_for_update is True
    assert faltoso.status == StatusAgendamento.FALTA.value

    # IDs inexistentes -> 404 AgendamentoNaoEncontradoError
    with pytest.raises(AgendamentoNaoEncontradoError):
        await service.concluir_agendamento(
            agendamento_id=uuid4(),
            profissional_id=prof_id,
        )
    with pytest.raises(AgendamentoNaoEncontradoError):
        await service.marcar_falta_agendamento(
            agendamento_id=uuid4(),
            profissional_id=prof_id,
        )
