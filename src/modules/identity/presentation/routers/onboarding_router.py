"""FastAPI router for progressive 2-phase patient onboarding."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from src.core.dependencies import TenantDep
from src.modules.identity.composition import OnboardingServiceDep
from src.modules.identity.presentation.dependencies import ValidarIntakeFase2Dep
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


@onboarding_router.post(
    "/fase-1",
    status_code=status.HTTP_201_CREATED,
    summary="Acolhimento clínico inicial (Fase 1)",
    description=(
        "Registra ou identifica o paciente com identificadores preliminares, queixa "
        "e hash do TCLE em tempo hábil (< 45s - NEC-01), emitindo token provisório."
    ),
)
async def intake_fase_1(
    body: Annotated[Fase1Request, Body()],
    tenant_id: TenantDep,
    service: OnboardingServiceDep,
) -> Fase1Response:
    """Execute Phase 1 rapid intake."""
    result = await service.realizar_fase_1(tenant_id, body)
    return Fase1Response.model_validate(result)


@onboarding_router.post(
    "/fase-2",
    status_code=status.HTTP_200_OK,
    summary="Enriquecimento regulatório de prontuário (Fase 2)",
    description=(
        "Completa o cadastro com os requisitos obrigatórios do CFM 1.821/2007 "
        "(nome da mãe, sexo biológico, endereço completo e alergias)."
    ),
)
async def enrichment_fase_2(
    body: Annotated[Fase2Request, Body()],
    tenant_id: TenantDep,
    service: OnboardingServiceDep,
    _auth: ValidarIntakeFase2Dep,
) -> Fase2Response:
    """Execute Phase 2 regulatory enrichment."""
    result = await service.realizar_fase_2(tenant_id, body)
    return Fase2Response.model_validate(result)
