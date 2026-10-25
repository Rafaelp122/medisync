"""FastAPI router for operational telemetry and configuration (ADR-001/ADR-008)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from src.core.dependencies import TenantDep
from src.modules.telemetry.composition import (
    ConfigPlantaoServiceDep,
    TelemetryServiceDep,
)
from src.modules.telemetry.presentation.dependencies import (
    TelemetryConfigAuthDep,
    TelemetryViewAuthDep,
)
from src.modules.telemetry.presentation.schemas import (
    ConfigPlantaoRequest,
    ConfigPlantaoResponse,
    PainelTelemetriaResponse,
)

telemetry_router = APIRouter(
    prefix="/telemetria",
    tags=["Telemetria"],
)


@telemetry_router.get(
    "/painel",
    status_code=status.HTTP_200_OK,
    summary="Painel operacional de telemetria em tempo real (RF-10)",
    description=(
        "Retorna métricas consolidadas do plantão médico (TME por prioridade, TMA "
        "médio e por médico, taxa de no-show, evasão e conformidade com SLA), "
        "com suporte a cache no Valkey e bypass sob demanda."
    ),
)
async def obter_painel_telemetria(
    tenant_id: TenantDep,
    telemetry_service: TelemetryServiceDep,
    _auth: TelemetryViewAuthDep,
    desconsiderar_cache: Annotated[
        bool,
        Query(description="Forçar recálculo ignorando o cache do Valkey"),
    ] = False,
) -> PainelTelemetriaResponse:
    """Fetch aggregated shift operational metrics and SLA compliance."""
    dto = await telemetry_service.obter_painel(
        organizacao_id=tenant_id,
        desconsiderar_cache=desconsiderar_cache,
    )
    return PainelTelemetriaResponse.model_validate(dto)


@telemetry_router.get(
    "/config-plantao",
    status_code=status.HTTP_200_OK,
    summary="Consulta parametrização de políticas do plantão (RF-09)",
    description=(
        "Consulta os parâmetros ativos do plantão para a organização "
        "(médicos planejados, fator alpha, cota diária, TMA padrão e metas de SLA). "
        "Se inexistente, inicializa e persiste a configuração default."
    ),
)
async def obter_configuracao_plantao(
    tenant_id: TenantDep,
    config_service: ConfigPlantaoServiceDep,
    _auth: TelemetryConfigAuthDep,
) -> ConfigPlantaoResponse:
    """Query current shift configuration policies for the organization."""
    dto = await config_service.obter_configuracao(organizacao_id=tenant_id)
    return ConfigPlantaoResponse.model_validate(dto)


@telemetry_router.put(
    "/config-plantao",
    status_code=status.HTTP_200_OK,
    summary="Atualiza parametrização de políticas do plantão (RF-09)",
    description=(
        "Atualiza as políticas e metas de SLA do plantão para a organização, "
        "validando limites e invariantes de domínio, invalidando o cache do painel "
        "e persistindo as alterações atomicamente."
    ),
)
async def atualizar_configuracao_plantao(
    body: Annotated[ConfigPlantaoRequest, Body()],
    tenant_id: TenantDep,
    config_service: ConfigPlantaoServiceDep,
    auth: TelemetryConfigAuthDep,
) -> ConfigPlantaoResponse:
    """Update shift operational parameters and SLA thresholds."""
    cmd = body.to_command(
        organizacao_id=tenant_id,
        atualizado_por_id=auth.usuario_id,
    )
    dto = await config_service.atualizar_configuracao(cmd)
    return ConfigPlantaoResponse.model_validate(dto)
