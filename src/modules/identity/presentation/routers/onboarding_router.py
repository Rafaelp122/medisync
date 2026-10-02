"""FastAPI router for progressive 2-phase patient onboarding."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import get_current_tenant_id
from src.core.database import get_db_session
from src.modules.identity.application.services.onboarding_service import (
    Fase1InputDTO,
    Fase2InputDTO,
    OnboardingService,
)
from src.modules.identity.domain.exceptions import TenantInvalidoError
from src.modules.identity.presentation.schemas import (
    Fase1Request,
    Fase1Response,
    Fase2Request,
    Fase2Response,
)

onboarding_router = APIRouter(
    prefix="/onboarding",
    tags=["Onboarding"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _get_required_tenant_id() -> int:
    tenant_id = get_current_tenant_id()
    if tenant_id is None or tenant_id <= 0:
        raise TenantInvalidoError(
            "Header 'X-Tenant-ID' ausente ou inválido. "
            "O acesso multi-tenant requer identificador positivo."
        )
    return tenant_id


TenantDep = Annotated[int, Depends(_get_required_tenant_id)]


@onboarding_router.post(
    "/fase-1",
    response_model=Fase1Response,
    status_code=status.HTTP_201_CREATED,
    summary="Acolhimento clínico inicial (Fase 1)",
    description=(
        "Registra ou identifica o paciente com identificadores preliminares, queixa "
        "e hash do TCLE em tempo hábil (< 45s - NEC-01), emitindo token provisório."
    ),
)
async def intake_fase_1(
    body: Fase1Request,
    tenant_id: TenantDep,
    session: SessionDep,
) -> Fase1Response:
    """Execute Phase 1 rapid intake."""
    service = OnboardingService()
    dto = Fase1InputDTO(
        nome_completo=body.nome_completo,
        data_nascimento=body.data_nascimento,
        telefone=body.telefone,
        queixa_principal=body.queixa_principal,
        tcle_hash=body.tcle_hash,
        cpf=body.cpf,
        cns=body.cns,
    )
    result = await service.realizar_fase_1(session, tenant_id, dto)

    return Fase1Response(
        paciente_id=result.paciente_id,
        token=result.token,
        status=result.status,
        mensagem=result.mensagem,
        is_novo_paciente=result.is_novo_paciente,
    )


@onboarding_router.post(
    "/fase-2",
    response_model=Fase2Response,
    status_code=status.HTTP_200_OK,
    summary="Enriquecimento regulatório de prontuário (Fase 2)",
    description=(
        "Completa o cadastro com os requisitos obrigatórios do CFM 1.821/2007 "
        "(nome da mãe, sexo biológico, endereço completo e alergias)."
    ),
)
async def enrichment_fase_2(
    body: Fase2Request,
    tenant_id: TenantDep,
    session: SessionDep,
) -> Fase2Response:
    """Execute Phase 2 regulatory enrichment."""
    service = OnboardingService()
    dto = Fase2InputDTO(
        paciente_id=body.paciente_id,
        nome_mae=body.nome_mae,
        sexo_biologico=body.sexo_biologico,
        cep=body.cep,
        logradouro=body.logradouro,
        numero=body.numero,
        bairro=body.bairro,
        cidade=body.cidade,
        estado=body.estado,
        alergias=body.alergias,
    )
    result = await service.realizar_fase_2(session, tenant_id, dto)

    return Fase2Response(
        paciente_id=result.paciente_id,
        nome_completo=result.nome_completo,
        nome_mae=result.nome_mae,
        sexo_biologico=result.sexo_biologico,
        cep=result.cep,
        logradouro=result.logradouro,
        numero=result.numero,
        bairro=result.bairro,
        cidade=result.cidade,
        estado=result.estado,
        alergias=result.alergias,
        status=result.status,
    )
