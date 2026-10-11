"""FastAPI router for patient intake and clinical triage admission."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from src.core.dependencies import TenantDep
from src.modules.queue.composition import AdmissaoServiceDep
from src.modules.queue.presentation.dependencies import AdmissaoPacienteAuthDep
from src.modules.queue.presentation.schemas import AdmissaoRequest, AdmissaoResponse

admissao_router = APIRouter(
    prefix="/fila",
    tags=["Fila"],
)


@admissao_router.post(
    "/admissao",
    status_code=status.HTTP_201_CREATED,
    summary="Admissão clínica e triagem no PA Virtual",
    description=(
        "Classifica o risco clínico pelo Protocolo Manchester/ACR, valida TCLE e "
        "backpressure estocástico, e persiste atomicamente atendimento e triagem. "
        "Requer credencial de autenticação válida (token provisório de "
        "acolhimento ou token de acesso) com posse sobre o paciente_id e "
        "organização para prevenir injeção anônima (Anti-IDOR)."
    ),
)
async def admitir_paciente(
    body: Annotated[AdmissaoRequest, Body()],
    tenant_id: TenantDep,
    service: AdmissaoServiceDep,
    _auth: AdmissaoPacienteAuthDep,
) -> AdmissaoResponse:
    """Execute patient intake, clinical triage, and queue admission."""
    cmd = body.to_command(organizacao_id=tenant_id)
    result = await service.admitir_paciente(cmd)
    return AdmissaoResponse.model_validate(result)
