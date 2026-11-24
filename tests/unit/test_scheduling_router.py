"""Testes unitários para rotas HTTP do módulo scheduling."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.errors import ForbiddenError
from src.main import create_app
from src.modules.scheduling.application.dtos import (
    AgendarConsultaCommand,
    CriarDisponibilidadeCommand,
    SlotDisponivelDTO,
)
from src.modules.scheduling.composition import get_scheduling_service
from src.modules.scheduling.domain.exceptions import (
    AgendamentoNaoEncontradoError,
    SlotIndisponivelError,
)
from src.modules.scheduling.domain.models import (
    ESPECIALIDADE_CATALOGO,
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeMetadata,
    StatusAgendamento,
)


class FakeSchedulingService:
    """Fake em memória para testes de contrato do router scheduling."""

    def __init__(self) -> None:
        self.disponibilidades: list[AgendaDisponibilidade] = []
        self.agendamentos: dict[UUID, Agendamento] = {}
        self.last_agendar_cmd: AgendarConsultaCommand | None = None

    def listar_especialidades(self) -> list[EspecialidadeMetadata]:
        return list(ESPECIALIDADE_CATALOGO.values())

    async def listar_slots_disponiveis(
        self,
        *,
        especialidade: str,
        data_inicio: date,
        data_fim: date,
    ) -> list[SlotDisponivelDTO]:
        inicio = datetime.combine(data_inicio, time(9, 0), tzinfo=UTC)
        return [
            SlotDisponivelDTO(
                profissional_id=uuid4(),
                especialidade=especialidade,
                slot_inicio=inicio,
                slot_fim=inicio + timedelta(minutes=50),
                duracao_minutos=50,
            )
        ]

    async def cadastrar_disponibilidade(
        self,
        cmd: CriarDisponibilidadeCommand,
    ) -> AgendaDisponibilidade:
        disp = AgendaDisponibilidade(
            profissional_id=cmd.profissional_id,
            especialidade=cmd.especialidade,
            dia_semana=cmd.dia_semana,
            hora_inicio=cmd.hora_inicio,
            hora_fim=cmd.hora_fim,
            duracao_minutos=cmd.duracao_minutos,
        )
        self.disponibilidades.append(disp)
        return disp

    async def agendar_consulta(self, cmd: AgendarConsultaCommand) -> Agendamento:
        self.last_agendar_cmd = cmd
        for existing in self.agendamentos.values():
            if (
                existing.profissional_id == cmd.profissional_id
                and existing.slot_inicio == cmd.slot_inicio
                and existing.status
                not in {
                    StatusAgendamento.CANCELADO.value,
                    StatusAgendamento.FALTA.value,
                }
            ):
                raise SlotIndisponivelError(
                    f"Slot '{cmd.slot_inicio.isoformat()}' já ocupado."
                )
        slot_fim = cmd.slot_fim or (cmd.slot_inicio + timedelta(minutes=50))
        ag = Agendamento(
            paciente_id=cmd.paciente_id,
            profissional_id=cmd.profissional_id,
            especialidade=cmd.especialidade,
            slot_inicio=cmd.slot_inicio,
            slot_fim=slot_fim,
            observacoes=cmd.observacoes,
        )
        self.agendamentos[ag.id] = ag
        return ag

    async def listar_agendamentos_paciente(
        self,
        *,
        paciente_id: UUID,
    ) -> list[Agendamento]:
        return [a for a in self.agendamentos.values() if a.paciente_id == paciente_id]

    async def cancelar_agendamento(
        self,
        *,
        agendamento_id: UUID,
        paciente_id: UUID,
    ) -> Agendamento:
        ag = self.agendamentos.get(agendamento_id)
        if ag is None:
            raise AgendamentoNaoEncontradoError(
                f"Agendamento '{agendamento_id}' não encontrado."
            )
        if ag.paciente_id != paciente_id:
            raise ForbiddenError(
                f"Agendamento '{agendamento_id}' não pertence a '{paciente_id}'."
            )
        ag.cancelar()
        return ag

    async def listar_agenda_profissional(
        self,
        *,
        profissional_id: UUID,
        data_inicio: date,
        data_fim: date,
    ) -> list[Agendamento]:
        return [
            a
            for a in self.agendamentos.values()
            if a.profissional_id == profissional_id
        ]

    def _buscar_do_profissional(
        self,
        agendamento_id: UUID,
        profissional_id: UUID,
    ) -> Agendamento:
        ag = self.agendamentos.get(agendamento_id)
        if ag is None:
            raise AgendamentoNaoEncontradoError(
                f"Agendamento '{agendamento_id}' não encontrado."
            )
        if ag.profissional_id != profissional_id:
            raise ForbiddenError(
                f"Agendamento '{agendamento_id}' pertence a outro profissional."
            )
        return ag

    async def iniciar_atendimento_agendado(
        self,
        *,
        agendamento_id: UUID,
        profissional_id: UUID,
        atendimento_id: UUID | None = None,
    ) -> Agendamento:
        ag = self._buscar_do_profissional(agendamento_id, profissional_id)
        ag.iniciar_atendimento(atendimento_id=atendimento_id)
        return ag

    async def concluir_agendamento(
        self,
        *,
        agendamento_id: UUID,
        profissional_id: UUID,
    ) -> Agendamento:
        ag = self._buscar_do_profissional(agendamento_id, profissional_id)
        ag.concluir()
        return ag

    async def marcar_falta_agendamento(
        self,
        *,
        agendamento_id: UUID,
        profissional_id: UUID,
    ) -> Agendamento:
        ag = self._buscar_do_profissional(agendamento_id, profissional_id)
        ag.marcar_falta()
        return ag


def _make_token(usuario_id: UUID, papel: str) -> str:
    return create_access_token(usuario_id=usuario_id, papel=papel)


@pytest.mark.asyncio
async def test_listar_especialidades_e_slots_200_ok() -> None:
    app = create_app()
    fake_service = FakeSchedulingService()
    app.dependency_overrides[get_scheduling_service] = lambda: fake_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_esp = await client.get("/api/v1/scheduling/especialidades")
        resp_slots = await client.get(
            "/api/v1/scheduling/slots?especialidade=PSICOLOGIA"
            "&data_inicio=2026-11-20&data_fim=2026-11-21",
        )

    assert resp_esp.status_code == 200
    codigos = {item["codigo"] for item in resp_esp.json()}
    assert codigos == {"PSICOLOGIA", "NUTRICAO"}

    assert resp_slots.status_code == 200
    assert len(resp_slots.json()) == 1
    assert resp_slots.json()[0]["especialidade"] == "PSICOLOGIA"


@pytest.mark.asyncio
async def test_fluxo_paciente_agendar_listar_cancelar_e_anti_idor() -> None:
    app = create_app()
    fake_service = FakeSchedulingService()
    app.dependency_overrides[get_scheduling_service] = lambda: fake_service

    paciente_id = uuid4()
    outro_paciente_id = uuid4()
    prof_id = uuid4()
    token_paciente = _make_token(paciente_id, Role.PACIENTE)
    token_outro = _make_token(outro_paciente_id, Role.PACIENTE)
    slot_inicio = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mesmo enviando paciente_id de terceiro, usa user.usuario_id (Anti-IDOR)
        resp_create = await client.post(
            "/api/v1/scheduling/agendamentos",
            headers={"Authorization": f"Bearer {token_paciente}"},
            json={
                "paciente_id": str(outro_paciente_id),
                "profissional_id": str(prof_id),
                "especialidade": "  PSICOLOGIA  ",
                "slot_inicio": slot_inicio.isoformat(),
                "observacoes": "  Retorno  ",
            },
        )
        assert resp_create.status_code == 201
        criado = resp_create.json()
        assert criado["paciente_id"] == str(paciente_id)
        assert criado["observacoes"] == "Retorno"
        assert fake_service.last_agendar_cmd is not None
        assert fake_service.last_agendar_cmd.paciente_id == paciente_id
        assert fake_service.last_agendar_cmd.especialidade == "PSICOLOGIA"

        # Double booking -> 409 Conflict
        resp_conflito = await client.post(
            "/api/v1/scheduling/agendamentos",
            headers={"Authorization": f"Bearer {token_outro}"},
            json={
                "profissional_id": str(prof_id),
                "especialidade": "PSICOLOGIA",
                "slot_inicio": slot_inicio.isoformat(),
            },
        )
        assert resp_conflito.status_code == 409

        # Listar meus agendamentos
        resp_me = await client.get(
            "/api/v1/scheduling/agendamentos/me",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert resp_me.status_code == 200
        assert len(resp_me.json()) == 1

        # Outro paciente não pode cancelar -> 403
        agendamento_id = criado["id"]
        resp_cancel_idor = await client.post(
            f"/api/v1/scheduling/agendamentos/{agendamento_id}/cancelar",
            headers={"Authorization": f"Bearer {token_outro}"},
        )
        assert resp_cancel_idor.status_code == 403

        # Dono cancela -> 200
        resp_cancel = await client.post(
            f"/api/v1/scheduling/agendamentos/{agendamento_id}/cancelar",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert resp_cancel.status_code == 200
        assert resp_cancel.json()["status"] == "CANCELADO"


@pytest.mark.asyncio
async def test_fluxo_profissional_disponibilidade_agenda_e_iniciar_rbac() -> None:
    app = create_app()
    fake_service = FakeSchedulingService()
    app.dependency_overrides[get_scheduling_service] = lambda: fake_service

    medico_id = uuid4()
    paciente_id = uuid4()
    token_medico = _make_token(medico_id, Role.MEDICO)
    token_paciente = _make_token(paciente_id, Role.PACIENTE)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Paciente não pode cadastrar disponibilidade -> 403
        resp_forbidden = await client.post(
            "/api/v1/scheduling/disponibilidades",
            headers={"Authorization": f"Bearer {token_paciente}"},
            json={
                "especialidade": "NUTRICAO",
                "dia_semana": 2,
                "hora_inicio": "08:00:00",
                "hora_fim": "12:00:00",
                "duracao_minutos": 30,
            },
        )
        assert resp_forbidden.status_code == 403

        # Horário com timezone na disponibilidade deve falhar com 422
        resp_tz = await client.post(
            "/api/v1/scheduling/disponibilidades",
            headers={"Authorization": f"Bearer {token_medico}"},
            json={
                "especialidade": "NUTRICAO",
                "dia_semana": 2,
                "hora_inicio": "08:00:00Z",
                "hora_fim": "12:00:00",
                "duracao_minutos": 30,
            },
        )
        assert resp_tz.status_code == 422

        # Médico cadastra disponibilidade (com whitespace em especialidade) -> 201
        resp_disp = await client.post(
            "/api/v1/scheduling/disponibilidades",
            headers={"Authorization": f"Bearer {token_medico}"},
            json={
                "especialidade": "  NUTRICAO  ",
                "dia_semana": 2,
                "hora_inicio": "08:00:00",
                "hora_fim": "12:00:00",
                "duracao_minutos": 30,
            },
        )
        assert resp_disp.status_code == 201
        assert resp_disp.json()["profissional_id"] == str(medico_id)
        assert resp_disp.json()["especialidade"] == "NUTRICAO"

        # Paciente agenda com o médico
        slot_inicio = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
        resp_ag = await client.post(
            "/api/v1/scheduling/agendamentos",
            headers={"Authorization": f"Bearer {token_paciente}"},
            json={
                "profissional_id": str(medico_id),
                "especialidade": "NUTRICAO",
                "slot_inicio": slot_inicio.isoformat(),
            },
        )
        assert resp_ag.status_code == 201
        agendamento_id = resp_ag.json()["id"]

        # Médico lista agenda do dia
        resp_agenda = await client.get(
            "/api/v1/scheduling/agenda/dia?data_inicio=2026-11-18&data_fim=2026-11-18",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_agenda.status_code == 200
        assert len(resp_agenda.json()) == 1

        # Médico inicia atendimento -> EM_ATENDIMENTO
        resp_iniciar = await client.post(
            f"/api/v1/scheduling/agendamentos/{agendamento_id}/iniciar",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_iniciar.status_code == 200
        assert resp_iniciar.json()["status"] == "EM_ATENDIMENTO"

        # Médico não pode criar agendamento de paciente -> 403
        resp_medico_agendar = await client.post(
            "/api/v1/scheduling/agendamentos",
            headers={"Authorization": f"Bearer {token_medico}"},
            json={
                "profissional_id": str(medico_id),
                "especialidade": "NUTRICAO",
                "slot_inicio": (slot_inicio + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp_medico_agendar.status_code == 403

        # Paciente não pode iniciar atendimento -> 403
        resp_paciente_iniciar = await client.post(
            f"/api/v1/scheduling/agendamentos/{agendamento_id}/iniciar",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert resp_paciente_iniciar.status_code == 403


def test_agenda_dia_documenta_default_utc_no_openapi() -> None:
    app = create_app()
    op = app.openapi()["paths"]["/api/v1/scheduling/agenda/dia"]["get"]
    assert "UTC" in op["summary"]
    desc_params = " ".join(p.get("description", "") for p in op["parameters"])
    assert "UTC" in desc_params


@pytest.mark.asyncio
async def test_rotas_concluir_e_falta_rbac_anti_idor_e_estados() -> None:
    app = create_app()
    fake_service = FakeSchedulingService()
    app.dependency_overrides[get_scheduling_service] = lambda: fake_service

    medico_id = uuid4()
    outro_medico_id = uuid4()
    paciente_id = uuid4()
    token_medico = _make_token(medico_id, Role.MEDICO)
    token_outro_medico = _make_token(outro_medico_id, Role.MEDICO)
    token_paciente = _make_token(paciente_id, Role.PACIENTE)

    slot_1 = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    slot_2 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    ag_1 = await fake_service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=medico_id,
            especialidade="PSICOLOGIA",
            slot_inicio=slot_1,
        )
    )
    ag_2 = await fake_service.agendar_consulta(
        AgendarConsultaCommand(
            paciente_id=uuid4(),
            profissional_id=medico_id,
            especialidade="PSICOLOGIA",
            slot_inicio=slot_2,
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Paciente não pode chamar /concluir nem /falta -> 403
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{ag_1.id}/concluir",
                headers={"Authorization": f"Bearer {token_paciente}"},
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{ag_2.id}/falta",
                headers={"Authorization": f"Bearer {token_paciente}"},
            )
        ).status_code == 403

        # Outro médico não pode concluir ou marcar falta -> 403
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{ag_1.id}/concluir",
                headers={"Authorization": f"Bearer {token_outro_medico}"},
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{ag_2.id}/falta",
                headers={"Authorization": f"Bearer {token_outro_medico}"},
            )
        ).status_code == 403

        # Concluir antes de iniciar (AGENDADO) -> 409
        resp_concluir_cedo = await client.post(
            f"/api/v1/scheduling/agendamentos/{ag_1.id}/concluir",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_concluir_cedo.status_code == 409
        assert resp_concluir_cedo.json()["code"] == "TRANSICAO_AGENDAMENTO_INVALIDA"

        # Iniciar + concluir -> 200 CONCLUIDO
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{ag_1.id}/iniciar",
                headers={"Authorization": f"Bearer {token_medico}"},
            )
        ).status_code == 200
        resp_concluir = await client.post(
            f"/api/v1/scheduling/agendamentos/{ag_1.id}/concluir",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_concluir.status_code == 200
        assert resp_concluir.json()["status"] == "CONCLUIDO"

        # Marcar falta em ag_2 (AGENDADO) -> 200 FALTA; repetir -> 409
        resp_falta = await client.post(
            f"/api/v1/scheduling/agendamentos/{ag_2.id}/falta",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_falta.status_code == 200
        assert resp_falta.json()["status"] == "FALTA"

        resp_falta_dup = await client.post(
            f"/api/v1/scheduling/agendamentos/{ag_2.id}/falta",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp_falta_dup.status_code == 409
        assert resp_falta_dup.json()["code"] == "TRANSICAO_AGENDAMENTO_INVALIDA"

        # ID inexistente -> 404 AgendamentoNaoEncontradoError
        inexistente = uuid4()
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{inexistente}/concluir",
                headers={"Authorization": f"Bearer {token_medico}"},
            )
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{inexistente}/falta",
                headers={"Authorization": f"Bearer {token_medico}"},
            )
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/scheduling/agendamentos/{inexistente}/cancelar",
                headers={"Authorization": f"Bearer {token_paciente}"},
            )
        ).status_code == 404
