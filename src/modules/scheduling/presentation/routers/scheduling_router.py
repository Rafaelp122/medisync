"""Router HTTP fino para agenda multiprofissional programada (eMulti)."""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Path, Query, status

from src.modules.scheduling.composition import SchedulingServiceDep
from src.modules.scheduling.presentation.dependencies import (
    PacienteSchedulingAuthDep,
    ProfissionalSchedulingAuthDep,
)
from src.modules.scheduling.presentation.schemas import (
    AgendamentoResponse,
    CriarAgendamentoRequest,
    CriarDisponibilidadeRequest,
    DisponibilidadeResponse,
    EspecialidadeResponse,
    IniciarAgendamentoRequest,
    SlotDisponivelResponse,
)

scheduling_router = APIRouter(
    prefix="/scheduling",
    tags=["Agendamento Multiprofissional"],
)


def _resolver_periodo_agenda(
    data: date | None,
    data_inicio: date | None,
    data_fim: date | None,
) -> tuple[date, date]:
    inicio = data_inicio or data or datetime.now(UTC).date()
    fim = data_fim or inicio
    return inicio, fim


@scheduling_router.get(
    "/especialidades",
    status_code=status.HTTP_200_OK,
    summary="Lista especialidades disponíveis na agenda multiprofissional",
)
async def listar_especialidades(
    service: SchedulingServiceDep,
) -> list[EspecialidadeResponse]:
    """Lista especialidades programadas com descrição e duração padrão."""
    itens = service.listar_especialidades()
    return [EspecialidadeResponse.model_validate(item) for item in itens]


@scheduling_router.get(
    "/slots",
    status_code=status.HTTP_200_OK,
    summary="Lista slots disponíveis por especialidade e período",
)
async def listar_slots(
    service: SchedulingServiceDep,
    especialidade: Annotated[
        str, Query(description="Especialidade (PSICOLOGIA ou NUTRICAO)")
    ],
    data_inicio: Annotated[date, Query(description="Data inicial (YYYY-MM-DD)")],
    data_fim: Annotated[date, Query(description="Data final (YYYY-MM-DD)")],
) -> list[SlotDisponivelResponse]:
    """Gera e retorna slots livres a partir das disponibilidades ativas."""
    slots = await service.listar_slots_disponiveis(
        especialidade=especialidade,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    return [SlotDisponivelResponse.model_validate(slot) for slot in slots]


@scheduling_router.post(
    "/agendamentos",
    status_code=status.HTTP_201_CREATED,
    summary="Agenda horário multiprofissional para o paciente autenticado",
)
async def criar_agendamento(
    body: Annotated[CriarAgendamentoRequest, Body()],
    user: PacienteSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> AgendamentoResponse:
    """Cria agendamento vinculado ao usuário autenticado prevenindo double-booking."""
    cmd = body.to_command(paciente_id=user.usuario_id)
    agendamento = await service.agendar_consulta(cmd)
    return AgendamentoResponse.model_validate(agendamento)


@scheduling_router.get(
    "/agendamentos/me",
    status_code=status.HTTP_200_OK,
    summary="Lista agendamentos do paciente autenticado",
)
async def listar_meus_agendamentos(
    user: PacienteSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> list[AgendamentoResponse]:
    """Retorna os agendamentos pertencentes ao paciente autenticado."""
    itens = await service.listar_agendamentos_paciente(
        paciente_id=user.usuario_id,
    )
    return [AgendamentoResponse.model_validate(item) for item in itens]


@scheduling_router.post(
    "/agendamentos/{agendamento_id}/cancelar",
    status_code=status.HTTP_200_OK,
    summary="Cancela um agendamento do paciente autenticado",
)
async def cancelar_agendamento(
    agendamento_id: Annotated[UUID, Path(description="ID do agendamento")],
    user: PacienteSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> AgendamentoResponse:
    """Cancela o agendamento se pertencer ao paciente autenticado."""
    agendamento = await service.cancelar_agendamento(
        agendamento_id=agendamento_id,
        paciente_id=user.usuario_id,
    )
    return AgendamentoResponse.model_validate(agendamento)


@scheduling_router.post(
    "/disponibilidades",
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra janela semanal de agenda do profissional autenticado",
)
async def cadastrar_disponibilidade(
    body: Annotated[CriarDisponibilidadeRequest, Body()],
    user: ProfissionalSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> DisponibilidadeResponse:
    """Registra janela recorrente de atendimento do profissional."""
    cmd = body.to_command(profissional_id=user.usuario_id)
    disponibilidade = await service.cadastrar_disponibilidade(cmd)
    return DisponibilidadeResponse.model_validate(disponibilidade)


@scheduling_router.get(
    "/agenda/dia",
    status_code=status.HTTP_200_OK,
    summary=(
        "Lista agendamentos do profissional no período "
        "(padrão sem filtro: data UTC corrente)"
    ),
)
async def listar_agenda_dia(
    user: ProfissionalSchedulingAuthDep,
    service: SchedulingServiceDep,
    data: Annotated[
        date | None,
        Query(
            description=(
                "Data única (YYYY-MM-DD). Quando omitida junto a data_inicio, "
                "assume a data UTC corrente."
            )
        ),
    ] = None,
    data_inicio: Annotated[
        date | None,
        Query(
            description=(
                "Data inicial (YYYY-MM-DD). Quando omitida junto a data, "
                "assume a data UTC corrente."
            )
        ),
    ] = None,
    data_fim: Annotated[
        date | None,
        Query(
            description=(
                "Data final (YYYY-MM-DD). Quando omitida, assume data_inicio "
                "(padrão: data UTC corrente)."
            )
        ),
    ] = None,
) -> list[AgendamentoResponse]:
    """Lista os agendamentos vinculados ao profissional autenticado (default UTC)."""
    inicio, fim = _resolver_periodo_agenda(data, data_inicio, data_fim)
    itens = await service.listar_agenda_profissional(
        profissional_id=user.usuario_id,
        data_inicio=inicio,
        data_fim=fim,
    )
    return [AgendamentoResponse.model_validate(item) for item in itens]


@scheduling_router.post(
    "/agendamentos/{agendamento_id}/iniciar",
    status_code=status.HTTP_200_OK,
    summary="Inicia atendimento clínico para um agendamento",
)
async def iniciar_atendimento_agendado(
    agendamento_id: Annotated[UUID, Path(description="ID do agendamento")],
    user: ProfissionalSchedulingAuthDep,
    service: SchedulingServiceDep,
    body: Annotated[IniciarAgendamentoRequest | None, Body()] = None,
) -> AgendamentoResponse:
    """Transiciona o agendamento do profissional para EM_ATENDIMENTO."""
    atendimento_id = body.atendimento_id if body is not None else None
    agendamento = await service.iniciar_atendimento_agendado(
        agendamento_id=agendamento_id,
        profissional_id=user.usuario_id,
        atendimento_id=atendimento_id,
    )
    return AgendamentoResponse.model_validate(agendamento)


@scheduling_router.post(
    "/agendamentos/{agendamento_id}/concluir",
    status_code=status.HTTP_200_OK,
    summary="Conclui atendimento clínico de um agendamento",
)
async def concluir_agendamento(
    agendamento_id: Annotated[UUID, Path(description="ID do agendamento")],
    user: ProfissionalSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> AgendamentoResponse:
    """Transiciona o agendamento do profissional de EM_ATENDIMENTO para CONCLUIDO."""
    agendamento = await service.concluir_agendamento(
        agendamento_id=agendamento_id,
        profissional_id=user.usuario_id,
    )
    return AgendamentoResponse.model_validate(agendamento)


@scheduling_router.post(
    "/agendamentos/{agendamento_id}/falta",
    status_code=status.HTTP_200_OK,
    summary="Registra ausência (falta) do paciente no agendamento",
)
async def marcar_falta_agendamento(
    agendamento_id: Annotated[UUID, Path(description="ID do agendamento")],
    user: ProfissionalSchedulingAuthDep,
    service: SchedulingServiceDep,
) -> AgendamentoResponse:
    """Transiciona o agendamento ativo do profissional para FALTA."""
    agendamento = await service.marcar_falta_agendamento(
        agendamento_id=agendamento_id,
        profissional_id=user.usuario_id,
    )
    return AgendamentoResponse.model_validate(agendamento)
