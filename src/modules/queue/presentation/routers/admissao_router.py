"""FastAPI router for patient intake and clinical triage admission."""

from fastapi import APIRouter, status

from src.core.dependencies import TenantDep
from src.modules.queue.composition import AdmissaoServiceDep
from src.modules.queue.presentation.schemas import AdmissaoRequest, AdmissaoResponse

admissao_router = APIRouter(
    prefix="/fila",
    tags=["Fila"],
)


@admissao_router.post(
    "/admissao",
    response_model=AdmissaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admissão clínica e triagem no PA Virtual",
    description=(
        "Classifica o risco clínico pelo Protocolo Manchester/ACR, valida TCLE e "
        "backpressure estocástico, e persiste atomicamente atendimento e triagem."
    ),
)
async def admitir_paciente(
    body: AdmissaoRequest,
    tenant_id: TenantDep,
    service: AdmissaoServiceDep,
) -> AdmissaoResponse:
    """Execute patient intake, clinical triage, and queue admission."""
    cmd = body.to_command(organizacao_id=tenant_id)
    result = await service.admitir_paciente(cmd)
    return AdmissaoResponse.model_validate(result)
