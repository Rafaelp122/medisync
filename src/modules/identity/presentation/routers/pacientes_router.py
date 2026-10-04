"""FastAPI router for patient and dependent management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status

from src.core.context import get_current_tenant_id
from src.core.database import DbSessionDep
from src.modules.identity.application.services.dependente_service import (
    DependenteService,
)
from src.modules.identity.domain.exceptions import TenantInvalidoError
from src.modules.identity.presentation.schemas import (
    CriarDependenteRequest,
    DependenteDetalheResponse,
    DependenteResponse,
)

pacientes_router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
)


def _get_required_tenant_id() -> int:
    tenant_id = get_current_tenant_id()
    if tenant_id is None or tenant_id <= 0:
        raise TenantInvalidoError(
            "Header 'X-Tenant-ID' ausente ou inválido. "
            "O acesso multi-tenant requer identificador positivo."
        )
    return tenant_id


TenantDep = Annotated[int, Depends(_get_required_tenant_id)]


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
) -> DependenteResponse:
    """Register or link a dependent to a titular patient."""
    service = DependenteService()
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
) -> list[DependenteDetalheResponse]:
    """List all dependents linked to the titular patient."""
    service = DependenteService()
    results = await service.listar_dependentes(
        session=session,
        organizacao_id=tenant_id,
        titular_id=id,
    )
    return [DependenteDetalheResponse.model_validate(d) for d in results]
