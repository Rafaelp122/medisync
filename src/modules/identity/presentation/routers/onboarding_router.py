"""FastAPI router for progressive 2-phase patient onboarding."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import get_current_tenant_id
from src.core.database import get_db_session
from src.modules.identity.application.services.onboarding_service import (
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
    result = await service.realizar_fase_1(session, tenant_id, body)
    return Fase1Response.model_validate(result)


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
    result = await service.realizar_fase_2(session, tenant_id, body)
    return Fase2Response.model_validate(result)
