"""FastAPI router for patient intake and clinical triage admission."""

from typing import Annotated

from fastapi import APIRouter, Body, Request, status

from src.core.dependencies import TenantDep
from src.modules.queue.composition import FilaServiceDep
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
    request: Request,
    tenant_id: TenantDep,
    service: FilaServiceDep,
    _auth: AdmissaoPacienteAuthDep,
) -> AdmissaoResponse:
    """Execute patient intake, clinical triage, and queue admission."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        raw_ip = forwarded.split(",")[0].strip()
    else:
        raw_ip = request.client.host if request.client else None
    ip_origem = raw_ip if raw_ip and raw_ip != "testclient" else None
    cmd = body.to_command(organizacao_id=tenant_id, ip_origem=ip_origem)
    result = await service.admitir_paciente(cmd)
    return AdmissaoResponse.model_validate(result)
