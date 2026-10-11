"""FastAPI router for medical queue allocation and next patient acquisition (RF-03)."""

from fastapi import APIRouter, status

from src.core.dependencies import TenantDep
from src.modules.queue.application.dtos import AdquirirProximoPacienteCommand
from src.modules.queue.composition import FilaServiceDep
from src.modules.queue.presentation.dependencies import MedicoPlantaoAuthDep
from src.modules.queue.presentation.schemas import ChamarProximoResponse

alocacao_router = APIRouter(
    prefix="/fila",
    tags=["Fila - Alocação Médica"],
)


@alocacao_router.post(
    "/chamar-proximo",
    status_code=status.HTTP_200_OK,
    summary="Chamar próximo paciente da fila clínica (RF-03)",
    description=(
        "Permite ao médico plantonista adquirir e alocar atomicamente via script Lua "
        "o próximo paciente de maior prioridade clínica da fila virtual (ZSET), com "
        "bloqueio de concorrência e TTL de chamada. Retorna 200 com os dados da "
        "chamada ou mensagem de fila vazia se não houver pacientes elegíveis."
    ),
)
async def chamar_proximo_paciente(
    tenant_id: TenantDep,
    medico: MedicoPlantaoAuthDep,
    fila_service: FilaServiceDep,
) -> ChamarProximoResponse:
    """Execute atomic acquisition and allocation of next patient in queue."""
    cmd = AdquirirProximoPacienteCommand(
        organizacao_id=tenant_id,
        medico_id=medico.usuario_id,
    )
    result = await fila_service.adquirir_proximo_paciente(cmd)
    if result is None:
        return ChamarProximoResponse(
            alocado=False,
            mensagem="Fila vazia. Não há pacientes aguardando atendimento no momento.",
        )
    return ChamarProximoResponse(
        alocado=True,
        atendimento_id=result.atendimento_id,
        medico_id=result.medico_id,
        status=result.status,
        chamada_iniciada_em=result.chamada_iniciada_em,
        ttl_segundos=result.ttl_segundos,
        mensagem="Paciente alocado com sucesso para chamada.",
    )
