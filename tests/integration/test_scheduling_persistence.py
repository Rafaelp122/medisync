"""Integration tests for scheduling persistence, Anti-IDOR, GiST, and FKs."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session_factory
from src.core.errors import ConflictError, ForbiddenError, NotFoundError
from src.modules.identity.domain.models import Paciente, Profissional
from src.modules.queue.composition import build_attendance_lookup_reader
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.scheduling.application.dtos import (
    AgendarConsultaCommand,
    CriarDisponibilidadeCommand,
)
from src.modules.scheduling.composition import build_scheduling_service
from src.modules.scheduling.domain.exceptions import SlotIndisponivelError
from src.modules.scheduling.domain.models import (
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeAgenda,
    StatusAgendamento,
)
from src.modules.scheduling.infrastructure.adapters.sql_scheduling_repository import (
    SqlSchedulingRepository,
)

from tests.factories.identity import make_paciente, make_profissional
from tests.factories.queue import make_atendimento

pytestmark = pytest.mark.usefixtures("clean_db")


class _RaceBypassRepo(SqlSchedulingRepository):
    """Repository double bypassing pre-check to test DB GiST constraints."""

    async def buscar_agendamento_conflitante(
        self,
        profissional_id: UUID,
        slot_inicio: datetime,
        slot_fim: datetime,
        *,
        paciente_id: UUID | None = None,
    ) -> Agendamento | None:
        return None


class _DispRaceBypassRepo(SqlSchedulingRepository):
    """Repository double bypassing availability overlap pre-check to hit GiST."""

    async def buscar_disponibilidade_profissional(
        self,
        profissional_id: UUID,
        especialidade: str | None,
        dia_semana: int,
    ) -> Sequence[AgendaDisponibilidade]:
        return []


def _futuro_dia_utc(dias: int = 7) -> datetime:
    base = (datetime.now(UTC) + timedelta(days=dias)).date()
    return datetime.combine(base, time(0, 0), tzinfo=UTC)


@pytest.mark.asyncio
async def test_anti_idor_ownership_scheduling_operations(
    db_session: AsyncSession,
) -> None:
    """Verify strict Anti-IDOR ownership across patients and professionals."""
    prof_a = make_profissional(
        cpf="51111111101",
        email="psi.a@org.local",
        papel="MEDICO",
        crm="111",
        crm_uf="SP",
    )
    pac_a = make_paciente(cpf="51111111102", telefone="11951111101")
    prof_b = make_profissional(
        cpf="52222222201",
        email="nutri.b@org.local",
        papel="MEDICO",
        crm="222",
        crm_uf="SP",
    )
    pac_b = make_paciente(cpf="52222222202", telefone="11952222201")
    db_session.add_all([prof_a, pac_a, prof_b, pac_b])
    await db_session.commit()

    dia_base = _futuro_dia_utc(7)

    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_a.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia_base.weekday(),
                hora_inicio=time(9, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        ag_a = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_a.id,
                profissional_id=prof_a.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=dia_base.replace(hour=9, minute=0),
            )
        )

        # Patient B attempting to cancel Patient A's appointment -> ForbiddenError
        with pytest.raises(ForbiddenError):
            await service.cancelar_agendamento(
                agendamento_id=ag_a.id,
                paciente_id=pac_b.id,
            )

        # Professional B cannot start Professional A's appointment -> ForbiddenError
        with pytest.raises(ForbiddenError):
            await service.iniciar_atendimento_agendado(
                agendamento_id=ag_a.id,
                profissional_id=prof_b.id,
            )

        # Patient B's listing remains isolated from Patient A's appointments
        assert await service.listar_agendamentos_paciente(paciente_id=pac_b.id) == []
        assert [
            a.id
            for a in await service.listar_agendamentos_paciente(paciente_id=pac_a.id)
        ] == [ag_a.id]


@pytest.mark.asyncio
async def test_sql_scheduling_repository_queries_reais(
    db_session: AsyncSession,
) -> None:
    """Validate all SqlSchedulingRepository queries against real PostgreSQL."""
    prof_1 = make_profissional(
        cpf="53111111101",
        email="prof1@sched.local",
        papel="MEDICO",
        crm="333",
        crm_uf="SP",
    )
    prof_2 = make_profissional(
        cpf="53111111102",
        email="prof2@sched.local",
        papel="MEDICO",
        crm="444",
        crm_uf="SP",
    )
    pac_1 = make_paciente(cpf="53222222201", telefone="11953111101")
    pac_2 = make_paciente(cpf="53222222202", telefone="11953111102")
    db_session.add_all([prof_1, prof_2, pac_1, pac_2])
    await db_session.commit()

    dia_base = _futuro_dia_utc(10)

    async with get_session_factory()() as session:
        repo = SqlSchedulingRepository(session)

        # Disponibilidades: 2 ativas PSICOLOGIA (ordem inversa), 1 inativa, 1 NUTRI
        d_tarde = AgendaDisponibilidade(
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=3,
            hora_inicio=time(14, 0),
            hora_fim=time(17, 0),
            duracao_minutos=50,
        )
        d_manha = AgendaDisponibilidade(
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fim=time(12, 0),
            duracao_minutos=50,
        )
        d_inativa = AgendaDisponibilidade(
            profissional_id=prof_2.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=2,
            hora_inicio=time(9, 0),
            hora_fim=time(12, 0),
            duracao_minutos=50,
            ativo=False,
        )
        d_nutri = AgendaDisponibilidade(
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.NUTRICAO,
            dia_semana=1,
            hora_inicio=time(13, 0),
            hora_fim=time(16, 0),
            duracao_minutos=30,
        )
        for disp in (d_tarde, d_manha, d_inativa, d_nutri):
            repo.adicionar_disponibilidade(disp)

        # Agendamentos em especialidades distintas e estados ativos/inativos
        ag_psi = Agendamento(
            paciente_id=pac_1.id,
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            slot_inicio=dia_base.replace(hour=9, minute=0),
            slot_fim=dia_base.replace(hour=9, minute=50),
            status=StatusAgendamento.AGENDADO,
        )
        ag_nutri_tarde = Agendamento(
            paciente_id=pac_1.id,
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.NUTRICAO,
            slot_inicio=dia_base.replace(hour=14, minute=0),
            slot_fim=dia_base.replace(hour=14, minute=30),
            status=StatusAgendamento.CONFIRMADO,
        )
        ag_cancelado = Agendamento(
            paciente_id=pac_2.id,
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            slot_inicio=dia_base.replace(hour=11, minute=0),
            slot_fim=dia_base.replace(hour=11, minute=50),
            status=StatusAgendamento.CANCELADO,
        )
        ag_falta = Agendamento(
            paciente_id=pac_2.id,
            profissional_id=prof_1.id,
            especialidade=EspecialidadeAgenda.NUTRICAO,
            slot_inicio=dia_base.replace(hour=15, minute=0),
            slot_fim=dia_base.replace(hour=15, minute=30),
            status=StatusAgendamento.FALTA,
        )
        ag_prof2 = Agendamento(
            paciente_id=pac_2.id,
            profissional_id=prof_2.id,
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            slot_inicio=dia_base.replace(hour=9, minute=0),
            slot_fim=dia_base.replace(hour=9, minute=50),
            status=StatusAgendamento.AGENDADO,
        )
        for ag in (ag_nutri_tarde, ag_psi, ag_cancelado, ag_falta, ag_prof2):
            repo.adicionar_agendamento(ag)

        await session.commit()

        # 1. listar_disponibilidades_ativas: apenas ativas da especialidade
        disps_psi = await repo.listar_disponibilidades_ativas(
            EspecialidadeAgenda.PSICOLOGIA.value
        )
        assert [d.id for d in disps_psi] == [d_manha.id, d_tarde.id]

        # 2. listar_agendamentos_ocupados: cross-especialidade e por profissional_ids
        ocupados = await repo.listar_agendamentos_ocupados(
            dia_base.replace(hour=8, minute=0),
            dia_base.replace(hour=16, minute=0),
            profissional_ids=[prof_1.id, prof_2.id],
        )
        assert {a.id for a in ocupados} == {
            ag_psi.id,
            ag_nutri_tarde.id,
            ag_prof2.id,
        }
        ocupados_prof1 = await repo.listar_agendamentos_ocupados(
            dia_base.replace(hour=8, minute=0),
            dia_base.replace(hour=16, minute=0),
            profissional_ids=[prof_1.id],
        )
        assert {a.id for a in ocupados_prof1} == {
            ag_psi.id,
            ag_nutri_tarde.id,
        }
        assert (
            await repo.listar_agendamentos_ocupados(
                dia_base.replace(hour=8, minute=0),
                dia_base.replace(hour=16, minute=0),
                profissional_ids=[],
            )
            == []
        )
        # Adjacente não colide
        assert (
            await repo.listar_agendamentos_ocupados(
                dia_base.replace(hour=9, minute=50),
                dia_base.replace(hour=10, minute=40),
                profissional_ids=[prof_1.id, prof_2.id],
            )
            == []
        )

        # 3. buscar_agendamento_conflitante: sobreposição cross-especialidade
        conflito_cross = await repo.buscar_agendamento_conflitante(
            prof_1.id,
            dia_base.replace(hour=14, minute=10),
            dia_base.replace(hour=15, minute=0),
        )
        assert conflito_cross is not None
        assert conflito_cross.id == ag_nutri_tarde.id

        assert (
            await repo.buscar_agendamento_conflitante(
                prof_1.id,
                dia_base.replace(hour=11, minute=0),
                dia_base.replace(hour=11, minute=50),
            )
            is None
        )

        # 4. buscar_agendamento_por_id(for_update=True)
        encontrado = await repo.buscar_agendamento_por_id(ag_psi.id, for_update=True)
        assert encontrado is not None
        assert encontrado.id == ag_psi.id

        # 5. listar_agendamentos_paciente (ordenado ASC por slot_inicio)
        p1_ags = await repo.listar_agendamentos_paciente(pac_1.id)
        assert [a.id for a in p1_ags] == [ag_psi.id, ag_nutri_tarde.id]

        # 6. listar_agendamentos_profissional ([inicio, fim) ordenado ASC)
        prof1_ags = await repo.listar_agendamentos_profissional(
            prof_1.id,
            dia_base.replace(hour=9, minute=0),
            dia_base.replace(hour=15, minute=0),
        )
        assert [a.id for a in prof1_ags] == [
            ag_psi.id,
            ag_cancelado.id,
            ag_nutri_tarde.id,
        ]


@pytest.mark.asyncio
async def test_buscar_agendamento_por_id_for_update_adquire_row_lock(
    db_session: AsyncSession,
) -> None:
    """Verify SELECT ... FOR UPDATE actually locks the row in PostgreSQL."""
    prof = make_profissional(
        cpf="54111111101", email="lock@sched.local", papel="MEDICO"
    )
    pac = make_paciente(cpf="54222222201", telefone="11954111101")
    db_session.add_all([prof, pac])
    await db_session.commit()

    dia = _futuro_dia_utc(5)
    ag = Agendamento(
        paciente_id=pac.id,
        profissional_id=prof.id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        slot_inicio=dia.replace(hour=9, minute=0),
        slot_fim=dia.replace(hour=9, minute=50),
    )
    db_session.add(ag)
    await db_session.commit()

    async with get_session_factory()() as s1, get_session_factory()() as s2:
        repo1 = SqlSchedulingRepository(s1)
        locked = await repo1.buscar_agendamento_por_id(ag.id, for_update=True)
        assert locked is not None

        with pytest.raises(DBAPIError) as exc_lock:
            await s2.execute(
                text("SELECT id FROM agendamentos WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": ag.id},
            )
        sqlstate = getattr(exc_lock.value.orig, "sqlstate", None)
        assert sqlstate == "55P03"
        await s2.rollback()
        await s1.rollback()


@pytest.mark.asyncio
async def test_gist_excl_agendamento_slot_ativo_e_liberacao_apos_cancelamento(
    db_session: AsyncSession,
) -> None:
    """Verify GiST blocks overlapping distinct starts and frees slot on cancel."""
    prof = make_profissional(
        cpf="55111111101", email="gist@sched.local", papel="MEDICO"
    )
    pac_1 = make_paciente(cpf="55222222201", telefone="11955111101")
    pac_2 = make_paciente(cpf="55222222202", telefone="11955111102")
    db_session.add_all([prof, pac_1, pac_2])
    await db_session.commit()

    dia_dt = _futuro_dia_utc(8)
    slot_0900 = dia_dt.replace(hour=9, minute=0)
    slot_0915 = dia_dt.replace(hour=9, minute=15)

    # 1. Cria janela [09:00, 12:00) e agenda [09:00, 09:50) via SchedulingService
    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia_dt.weekday(),
                hora_inicio=time(9, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        ag_0900 = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_1.id,
                profissional_id=prof.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=slot_0900,
            )
        )
        ag_0900_id = ag_0900.id

    # 2. Simula grade deslocada [09:15, 11:00) e corrida na pré-checagem:
    #    o banco deve barrar [09:15, 10:05) via GiST excl_agendamento_slot_ativo
    async with get_session_factory()() as session:
        disp_antiga = (
            await session.execute(
                select(AgendaDisponibilidade).where(
                    AgendaDisponibilidade.profissional_id == prof.id
                )
            )
        ).scalar_one()
        disp_antiga.ativo = False
        session.add(
            AgendaDisponibilidade(
                profissional_id=prof.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA,
                dia_semana=dia_dt.weekday(),
                hora_inicio=time(9, 15),
                hora_fim=time(11, 5),
                duracao_minutos=50,
            )
        )
        await session.commit()

        # Direct DB check: 23P01 + excl_agendamento_slot_ativo
        session.add(
            Agendamento(
                paciente_id=pac_2.id,
                profissional_id=prof.id,
                especialidade=EspecialidadeAgenda.NUTRICAO,
                slot_inicio=slot_0915,
                slot_fim=slot_0915 + timedelta(minutes=50),
            )
        )
        with pytest.raises(IntegrityError) as exc_gist:
            await session.commit()
        assert getattr(exc_gist.value.orig, "sqlstate", None) == "23P01"
        constraint = getattr(
            getattr(exc_gist.value.orig, "diag", None), "constraint_name", None
        )
        assert constraint == "excl_agendamento_slot_ativo"
        await session.rollback()

        # Service translation: 23P01 -> SlotIndisponivelError
        race_service = build_scheduling_service(
            session=session,
            repository=_RaceBypassRepo(session),
        )
        with pytest.raises(SlotIndisponivelError, match="23P01"):
            await race_service.agendar_consulta(
                AgendarConsultaCommand(
                    paciente_id=pac_2.id,
                    profissional_id=prof.id,
                    especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                    slot_inicio=slot_0915,
                )
            )

    # 3. Cancelar [09:00, 09:50) libera o intervalo na constraint GiST para nova reserva
    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        cancelado = await service.cancelar_agendamento(
            agendamento_id=ag_0900_id,
            paciente_id=pac_1.id,
        )
        assert cancelado.status == StatusAgendamento.CANCELADO.value

        novo_ag = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_2.id,
                profissional_id=prof.id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=slot_0915,
            )
        )
        assert novo_ag.status == StatusAgendamento.AGENDADO.value
        assert novo_ag.slot_inicio == slot_0915
        assert novo_ag.slot_fim == slot_0915 + timedelta(minutes=50)


@pytest.mark.asyncio
async def test_scheduling_foreign_keys_23503_e_ondelete_restrict(
    db_session: AsyncSession,
) -> None:
    """Verify FK 23503 on missing refs and ondelete=RESTRICT when deleting parents."""
    prof = make_profissional(cpf="56111111101", email="fk@sched.local", papel="MEDICO")
    pac = make_paciente(cpf="56222222201", telefone="11956111101")
    db_session.add_all([prof, pac])
    await db_session.commit()

    atendimento = make_atendimento(
        paciente_id=pac.id,
        medico_id=prof.id,
        status=StatusAtendimento.EM_ATENDIMENTO,
    )
    db_session.add(atendimento)
    await db_session.commit()

    prof_id = prof.id
    pac_id = pac.id
    atendimento_id = atendimento.id

    dia_dt = _futuro_dia_utc(6)
    slot_ini = dia_dt.replace(hour=10, minute=0)
    slot_fim = dia_dt.replace(hour=10, minute=50)

    # 1. FK inexistente em AgendaDisponibilidade (profissional_id)
    db_session.add(
        AgendaDisponibilidade(
            profissional_id=uuid4(),
            especialidade=EspecialidadeAgenda.PSICOLOGIA,
            dia_semana=dia_dt.weekday(),
            hora_inicio=time(10, 0),
            hora_fim=time(12, 0),
            duracao_minutos=50,
        )
    )
    with pytest.raises(IntegrityError) as exc_disp_fk:
        await db_session.commit()
    assert getattr(exc_disp_fk.value.orig, "sqlstate", None) == "23503"
    await db_session.rollback()

    # 2. FK inexistente em Agendamento (profissional_id, paciente_id, atendimento_id)
    bad_refs: tuple[tuple[UUID, UUID, UUID | None], ...] = (
        (uuid4(), pac_id, None),
        (prof_id, uuid4(), None),
        (prof_id, pac_id, uuid4()),
    )
    for bad_prof_id, bad_pac_id, bad_atend_id in bad_refs:
        db_session.add(
            Agendamento(
                paciente_id=bad_pac_id,
                profissional_id=bad_prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA,
                slot_inicio=slot_ini,
                slot_fim=slot_fim,
                atendimento_id=bad_atend_id,
            )
        )
        with pytest.raises(IntegrityError) as exc_ag_fk:
            await db_session.commit()
        assert getattr(exc_ag_fk.value.orig, "sqlstate", None) == "23503"
        await db_session.rollback()

    # 3. SchedulingService traduz 23503 de paciente_id inexistente para NotFoundError
    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia_dt.weekday(),
                hora_inicio=time(10, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        with pytest.raises(NotFoundError, match="não localizado"):
            await service.agendar_consulta(
                AgendarConsultaCommand(
                    paciente_id=uuid4(),
                    profissional_id=prof_id,
                    especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                    slot_inicio=slot_ini,
                )
            )

        ag_real = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=slot_ini,
            )
        )
        iniciado = await service.iniciar_atendimento_agendado(
            agendamento_id=ag_real.id,
            profissional_id=prof_id,
            atendimento_id=atendimento_id,
        )
        assert iniciado.status == StatusAgendamento.EM_ATENDIMENTO.value
        assert iniciado.atendimento_id == atendimento_id

    # 4. ondelete="RESTRICT": bloqueia deleção de pais com agendamentos ativos
    restrict_targets: tuple[
        tuple[type[Atendimento | Paciente | Profissional], UUID], ...
    ] = (
        (Atendimento, atendimento_id),
        (Paciente, pac_id),
        (Profissional, prof_id),
    )
    for target_cls, target_id in restrict_targets:
        parent_obj = await db_session.get(target_cls, target_id)
        assert parent_obj is not None
        await db_session.delete(parent_obj)
        with pytest.raises(IntegrityError) as exc_restrict:
            await db_session.commit()
        assert getattr(exc_restrict.value.orig, "sqlstate", None) == "23503"
        await db_session.rollback()


@pytest.mark.asyncio
async def test_iniciar_atendimento_agendado_duplicado_lanca_conflict_409_com_ids(
    db_session: AsyncSession,
) -> None:
    """Verify duplicate atendimento_id raises 409 ConflictError with offending IDs."""
    prof = make_profissional(
        cpf="57111111101", email="dup.atend@sched.local", papel="MEDICO"
    )
    pac = make_paciente(cpf="57222222201", telefone="11957111101")
    db_session.add_all([prof, pac])
    await db_session.commit()

    atendimento = make_atendimento(
        paciente_id=pac.id,
        medico_id=prof.id,
        status=StatusAtendimento.EM_ATENDIMENTO,
    )
    db_session.add(atendimento)
    await db_session.commit()

    prof_id = prof.id
    pac_id = pac.id
    atend_id = atendimento.id
    dia = _futuro_dia_utc(9)

    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia.weekday(),
                hora_inicio=time(8, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        ag_1 = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=dia.replace(hour=8, minute=0),
            )
        )
        ag_2 = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=dia.replace(hour=8, minute=50),
            )
        )
        ag_2_id = ag_2.id

        await service.iniciar_atendimento_agendado(
            agendamento_id=ag_1.id,
            profissional_id=prof_id,
            atendimento_id=atend_id,
        )

        with pytest.raises(ConflictError) as exc_dup:
            await service.iniciar_atendimento_agendado(
                agendamento_id=ag_2_id,
                profissional_id=prof_id,
                atendimento_id=atend_id,
            )
        assert exc_dup.value.status_code == 409
        assert str(atend_id) in str(exc_dup.value)
        assert str(ag_2_id) in str(exc_dup.value)

        # Rollback preservou ag_2 em AGENDADO sem corromper sessão
        ag_2_reloaded = await service._repository.buscar_agendamento_por_id(  # pyright: ignore[reportPrivateUsage]
            ag_2_id
        )
        assert ag_2_reloaded is not None
        assert ag_2_reloaded.status == StatusAgendamento.AGENDADO.value
        assert ag_2_reloaded.atendimento_id is None


@pytest.mark.asyncio
async def test_disponibilidade_sobreposta_gist_e_concorrencia_lock(
    db_session: AsyncSession,
) -> None:
    """Verify excl_agenda_disp_sobreposicao and advisory lock under concurrency."""
    prof = make_profissional(
        cpf="58111111101", email="disp.lock@sched.local", papel="MEDICO"
    )
    db_session.add(prof)
    await db_session.commit()
    prof_id = prof.id
    dia_semana = 2

    # 1. Bypass de pré-checagem aciona GiST excl_agenda_disp_sobreposicao -> 409
    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia_semana,
                hora_inicio=time(8, 0),
                hora_fim=time(11, 0),
                duracao_minutos=50,
            )
        )

        race_service = build_scheduling_service(
            session=session,
            repository=_DispRaceBypassRepo(session),
        )
        with pytest.raises(SlotIndisponivelError, match="23P01"):
            await race_service.cadastrar_disponibilidade(
                CriarDisponibilidadeCommand(
                    profissional_id=prof_id,
                    especialidade=EspecialidadeAgenda.NUTRICAO.value,
                    dia_semana=dia_semana,
                    hora_inicio=time(10, 0),
                    hora_fim=time(12, 0),
                    duracao_minutos=30,
                )
            )

    # 2. Corrida concorrente real com pg_advisory_xact_lock: 1 vence, 1 recebe 409
    async def _cadastrar_concorrente(hora_ini: time, hora_fim: time) -> str:
        async with get_session_factory()() as sess:
            srv = build_scheduling_service(session=sess)
            try:
                await srv.cadastrar_disponibilidade(
                    CriarDisponibilidadeCommand(
                        profissional_id=prof_id,
                        especialidade=EspecialidadeAgenda.NUTRICAO.value,
                        dia_semana=dia_semana,
                        hora_inicio=hora_ini,
                        hora_fim=hora_fim,
                        duracao_minutos=30,
                    )
                )
            except SlotIndisponivelError:
                return "CONFLITO"
            else:
                return "OK"

    resultados = await asyncio.gather(
        _cadastrar_concorrente(time(13, 0), time(15, 0)),
        _cadastrar_concorrente(time(14, 0), time(16, 0)),
    )
    assert sorted(resultados) == ["CONFLITO", "OK"]


@pytest.mark.asyncio
async def test_gist_excl_agendamento_paciente_ativo_bloqueia_double_booking(
    db_session: AsyncSession,
) -> None:
    """Verify patient cannot book overlapping slots across distinct professionals."""
    prof_1 = make_profissional(
        cpf="59111111101", email="p1.pac@sched.local", papel="MEDICO"
    )
    prof_2 = make_profissional(
        cpf="59111111102", email="p2.pac@sched.local", papel="MEDICO"
    )
    pac = make_paciente(cpf="59222222201", telefone="11959111101")
    db_session.add_all([prof_1, prof_2, pac])
    await db_session.commit()

    prof_1_id = prof_1.id
    prof_2_id = prof_2.id
    pac_id = pac.id
    dia = _futuro_dia_utc(11)

    async with get_session_factory()() as session:
        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_1_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia.weekday(),
                hora_inicio=time(9, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_2_id,
                especialidade=EspecialidadeAgenda.NUTRICAO.value,
                dia_semana=dia.weekday(),
                hora_inicio=time(9, 0),
                hora_fim=time(12, 0),
                duracao_minutos=30,
            )
        )
        ag_1 = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_1_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=dia.replace(hour=9, minute=0),
            )
        )
        ag_1_id = ag_1.id

        # Pré-checagem bloqueia double-booking do paciente com outro profissional
        with pytest.raises(SlotIndisponivelError, match=str(pac_id)):
            await service.agendar_consulta(
                AgendarConsultaCommand(
                    paciente_id=pac_id,
                    profissional_id=prof_2_id,
                    especialidade=EspecialidadeAgenda.NUTRICAO.value,
                    slot_inicio=dia.replace(hour=9, minute=30),
                )
            )

        # Bypass de pré-checagem aciona constraint GiST excl_agendamento_paciente_ativo
        race_service = build_scheduling_service(
            session=session,
            repository=_RaceBypassRepo(session),
        )
        with pytest.raises(
            SlotIndisponivelError, match="excl_agendamento_paciente_ativo"
        ):
            await race_service.agendar_consulta(
                AgendarConsultaCommand(
                    paciente_id=pac_id,
                    profissional_id=prof_2_id,
                    especialidade=EspecialidadeAgenda.NUTRICAO.value,
                    slot_inicio=dia.replace(hour=9, minute=30),
                )
            )

        # Marcar FALTA libera a janela temporal do paciente na constraint GiST
        faltoso = await service.marcar_falta_agendamento(
            agendamento_id=ag_1_id,
            profissional_id=prof_1_id,
        )
        assert faltoso.status == StatusAgendamento.FALTA.value

        ag_2 = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_2_id,
                especialidade=EspecialidadeAgenda.NUTRICAO.value,
                slot_inicio=dia.replace(hour=9, minute=30),
            )
        )
        assert ag_2.profissional_id == prof_2_id


@pytest.mark.asyncio
async def test_concluir_agendamento_e_sql_attendance_snapshot_reader(
    db_session: AsyncSession,
) -> None:
    """Verify concluir persistence and lightweight SQL attendance snapshot reader."""
    prof = make_profissional(
        cpf="60111111101", email="reader.sched@sched.local", papel="MEDICO"
    )
    pac = make_paciente(cpf="60222222201", telefone="11960111101")
    db_session.add_all([prof, pac])
    await db_session.commit()

    atend_ativo = make_atendimento(
        paciente_id=pac.id,
        medico_id=prof.id,
        status=StatusAtendimento.EM_ATENDIMENTO,
    )
    atend_concluido = make_atendimento(
        paciente_id=pac.id,
        medico_id=prof.id,
        status=StatusAtendimento.CONCLUIDO,
    )
    db_session.add_all([atend_ativo, atend_concluido])
    await db_session.commit()

    prof_id = prof.id
    pac_id = pac.id
    atend_ativo_id = atend_ativo.id
    atend_concluido_id = atend_concluido.id
    dia = _futuro_dia_utc(12)

    async with get_session_factory()() as session:
        reader = build_attendance_lookup_reader(session=session)
        snap_ativo = await reader.buscar_atendimento(atend_ativo_id)
        snap_concluido = await reader.buscar_atendimento(atend_concluido_id)
        assert snap_ativo is not None
        assert snap_ativo.paciente_id == pac_id
        assert snap_ativo.medico_id == prof_id
        assert snap_ativo.is_terminal is False
        assert snap_concluido is not None
        assert snap_concluido.is_terminal is True
        assert await reader.buscar_atendimento(uuid4()) is None

        service = build_scheduling_service(session=session)
        await service.cadastrar_disponibilidade(
            CriarDisponibilidadeCommand(
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                dia_semana=dia.weekday(),
                hora_inicio=time(10, 0),
                hora_fim=time(12, 0),
                duracao_minutos=50,
            )
        )
        ag = await service.agendar_consulta(
            AgendarConsultaCommand(
                paciente_id=pac_id,
                profissional_id=prof_id,
                especialidade=EspecialidadeAgenda.PSICOLOGIA.value,
                slot_inicio=dia.replace(hour=10, minute=0),
            )
        )
        await service.iniciar_atendimento_agendado(
            agendamento_id=ag.id,
            profissional_id=prof_id,
            atendimento_id=atend_ativo_id,
        )
        concluido = await service.concluir_agendamento(
            agendamento_id=ag.id,
            profissional_id=prof_id,
        )
        assert concluido.status == StatusAgendamento.CONCLUIDO.value
