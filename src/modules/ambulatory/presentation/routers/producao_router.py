"""FastAPI router for SUS ambulatory production and BPA-I export (ADR-001/ADR-008)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from src.core.dependencies import TenantDep
from src.modules.ambulatory.composition import ProducaoServiceDep
from src.modules.ambulatory.presentation.dependencies import AmbulatoryAuthDep
from src.modules.ambulatory.presentation.schemas import (
    ListaProducaoAmbulatorialResponse,
)

producao_router = APIRouter(
    prefix="/ambulatory/producao",
    tags=["Produção Ambulatorial SUS"],
)


@producao_router.get(
    "",
    response_model=ListaProducaoAmbulatorialResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista a produção ambulatorial consolidada por competência (RF-08, US-11)",
    description=(
        "Consulta registros consolidados de faturamento público SUS (BPA-I / SISAB) "
        "para prestação de contas do consórcio municipal e incentivo eMulti."
    ),
)
async def listar_producao(
    tenant_id: TenantDep,
    producao_service: ProducaoServiceDep,
    _auth: AmbulatoryAuthDep,
    competencia: Annotated[
        str,
        Query(description="Competência de referência no formato YYYYMM"),
    ],
    page: Annotated[int, Query(ge=1, description="Número da página")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Tamanho da página")] = 50,
) -> ListaProducaoAmbulatorialResponse:
    """List consolidated SUS ambulatory production for the given competence."""
    dto = await producao_service.listar_producao_por_competencia(
        organizacao_id=tenant_id,
        competencia=competencia,
        page=page,
        size=size,
    )
    return ListaProducaoAmbulatorialResponse.model_validate(dto)


@producao_router.get(
    "/exportar",
    status_code=status.HTTP_200_OK,
    summary="Gera e faz download do arquivo magnético BPA-I do SIA-SUS (RF-08, US-11)",
    description=(
        "Gera o arquivo de texto posicional com colunas fixas e checksum cbc-smt-vrf "
        "formatado para importação no aplicativo BPA-Mag do DATASUS."
    ),
)
async def exportar_bpa(
    tenant_id: TenantDep,
    producao_service: ProducaoServiceDep,
    _auth: AmbulatoryAuthDep,
    competencia: Annotated[
        str,
        Query(description="Competência de referência no formato YYYYMM"),
    ],
) -> Response:
    """Generate and stream DATASUS positional BPA-I magnetic file."""
    dto = await producao_service.gerar_arquivo_bpa_i(
        organizacao_id=tenant_id,
        competencia=competencia,
    )
    return Response(
        content=dto.conteudo,
        media_type="text/plain; charset=ascii",
        headers={
            "Content-Disposition": f'attachment; filename="{dto.nome_arquivo}"',
        },
    )
