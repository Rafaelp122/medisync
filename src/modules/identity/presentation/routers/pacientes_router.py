"""FastAPI router for patient and dependent management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, status

from src.core.database import DbSessionDep
from src.core.dependencies import TenantDep
from src.modules.identity.composition import DependenteServiceDep
from src.modules.identity.presentation.schemas import (
    CriarDependenteRequest,
    DependenteDetalheResponse,
    DependenteResponse,
)

pacientes_router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
)


@pacientes_router.post(
    "/{id}/dependentes",
    response_model=DependenteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar ou vincular dependente",
    description=(
        "Vincula um dependente legal ou menor ao paciente titular, "
        "com validação anti-reflexiva."
    ),
)
async def cadastrar_dependente(
    id: Annotated[UUID, Path(description="ID do paciente titular")],
    body: CriarDependenteRequest,
    tenant_id: TenantDep,
    session: DbSessionDep,
    service: DependenteServiceDep,
) -> DependenteResponse:
    """Register or link a dependent to a titular patient."""
    result = await service.adicionar_dependente(
        session=session,
        organizacao_id=tenant_id,
        titular_id=id,
        dados=body,
    )
    return DependenteResponse.model_validate(result)


@pacientes_router.get(
    "/{id}/dependentes",
    response_model=list[DependenteDetalheResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar dependentes do titular",
    description=(
        "Recupera a lista de todos os dependentes vinculados "
        "ao paciente titular na organização."
    ),
)
async def listar_dependentes(
    id: Annotated[UUID, Path(description="ID do paciente titular")],
    tenant_id: TenantDep,
    session: DbSessionDep,
    service: DependenteServiceDep,
) -> list[DependenteDetalheResponse]:
    """List all dependents linked to the titular patient."""
    results = await service.listar_dependentes(
        session=session,
        organizacao_id=tenant_id,
        titular_id=id,
    )
    return [DependenteDetalheResponse.model_validate(d) for d in results]
