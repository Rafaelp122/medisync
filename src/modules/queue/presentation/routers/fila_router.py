"""FastAPI router for queue position, cancellation, and clinical deterioration."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Path, status

from src.core.dependencies import TenantDep
from src.modules.queue.composition import FilaServiceDep
from src.modules.queue.presentation.dependencies import (
    PosseAtendimentoPathAuthDep,
    PosseAtendimentoPioraAuthDep,
)
from src.modules.queue.presentation.schemas import (
    CancelarFilaRequest,
    CancelarFilaResponse,
    PioraClinicaRequest,
    PioraClinicaResponse,
    PosicaoFilaResponse,
)

fila_router = APIRouter(
    prefix="/fila",
    tags=["Fila - Paciente"],
)


@fila_router.get(
    "/posicao/{atendimento_id}",
    status_code=status.HTTP_200_OK,
    summary="Consultar posição e tempo estimado na fila virtual",
    description=(
        "Retorna a posição ordinal do paciente na fila virtual (ZSET) e o tempo de "
        "espera estimado baseado no TMA, exigindo token válido com posse sobre "
        "o atendimento (Anti-IDOR)."
    ),
)
async def obter_posicao_fila(
    atendimento_id: Annotated[UUID, Path(description="ID do atendimento")],
    tenant_id: TenantDep,
    fila_service: FilaServiceDep,
    _auth: PosseAtendimentoPathAuthDep,
) -> PosicaoFilaResponse:
    """Query queue position and estimated wait time for patient."""
    result = await fila_service.obter_posicao_e_estimativa(
        organizacao_id=tenant_id,
        atendimento_id=atendimento_id,
    )
    return PosicaoFilaResponse.model_validate(result)


@fila_router.post(
    "/cancelar/{atendimento_id}",
    status_code=status.HTTP_200_OK,
    summary="Cancelamento voluntário de atendimento na fila (RN06)",
    description=(
        "Permite ao paciente cancelar voluntariamente seu atendimento na fila. "
        "Remove atomicamente do ZSET e transiciona o status para CANCELADO no banco."
    ),
)
async def cancelar_atendimento_fila(
    atendimento_id: Annotated[UUID, Path(description="ID do atendimento")],
    tenant_id: TenantDep,
    fila_service: FilaServiceDep,
    _auth: PosseAtendimentoPathAuthDep,
    body: Annotated[CancelarFilaRequest | None, Body()] = None,
) -> CancelarFilaResponse:
    """Execute voluntary cancellation of attendance in virtual queue."""
    motivo = body.motivo if body is not None else "Desistência voluntária pelo paciente"
    result = await fila_service.cancelar_atendimento_paciente(
        organizacao_id=tenant_id,
        atendimento_id=atendimento_id,
        motivo=motivo,
    )
    return CancelarFilaResponse.model_validate(result)


@fila_router.post(
    "/piora",
    status_code=status.HTTP_200_OK,
    summary="Salvaguarda clínica: notificação de piora clínica na fila (RF-06)",
    description=(
        "Permite ao paciente comunicar agravamento dos sintomas enquanto aguarda. "
        "Reavalia o risco pelo motor de triagem: se emergência (Vermelho), dispara "
        "alerta SAMU; caso contrário, recalcula score e reposiciona na fila."
    ),
)
async def comunicar_piora_clinica(
    body: Annotated[PioraClinicaRequest, Body()],
    tenant_id: TenantDep,
    fila_service: FilaServiceDep,
    _auth: PosseAtendimentoPioraAuthDep,
) -> PioraClinicaResponse:
    """Execute clinical re-evaluation and queue re-prioritization on deterioration."""
    cmd = body.to_command(organizacao_id=tenant_id)
    result = await fila_service.processar_piora_clinica(cmd)
    return PioraClinicaResponse.model_validate(result)
