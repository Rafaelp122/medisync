"""Asynchronous health insurance and SUS eligibility verification task (RF-02, RN03)."""

import logging
from typing import Any
from uuid import UUID

from src.core.context import tenant_context
from src.core.errors import NotFoundError
from src.modules.billing import (
    ElegibilidadeNotifierPort,
    ElegibilidadeService,
    EligibilityProviderPort,
    PrivateInsuranceGatewayAdapter,
    RequisicaoElegibilidade,
    SusEligibilityAdapter,
)
from src.modules.identity.composition import get_identity_reader
from src.modules.queue.composition import build_fila_service_for_session
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.eligibility")


@monitored_task
async def validar_elegibilidade_task(
    ctx: dict[str, Any],
    organizacao_id: int,
    atendimento_id: str,
    paciente_id: str,
    cpf: str | None = None,
    cns: str | None = None,
    operadora_id: str | None = None,
    numero_carteirinha: str | None = None,
    modo_publico_sus: bool | None = None,
    provider: EligibilityProviderPort | None = None,
    notifier: ElegibilidadeNotifierPort | None = None,
) -> dict[str, Any]:
    """Validates insurance or SUS eligibility asynchronously in the background.

    Flow:
    1. Determines public SUS mode vs private insurance gateway.
    2. Executes validation (instant no-op for SUS, 15s timeout for private).
    3. On approval:
       - Promotes attendance to APTO_PARA_CHAMADA and ingests into queue.
    4. On rejection / timeout:
       - Preserves attendance status in TRIADO_AGUARDANDO_ELEGIBILIDADE (RF-05).
       - Dispatches alert notification to patient waiting room for regularisation.
    """
    atend_uuid = UUID(atendimento_id)
    paciente_uuid = UUID(paciente_id)

    with tenant_context(organizacao_id):
        async with get_db_session_from_ctx(ctx) as session:
            # 1. Discover mode via IdentityReaderPort if not provided
            is_sus = modo_publico_sus
            if is_sus is None:
                identity_reader = get_identity_reader(session)
                is_sus = await identity_reader.obter_modo_sus(organizacao_id)

            # 2. Select adapter
            resolved_provider = provider
            if resolved_provider is None:
                if is_sus:
                    resolved_provider = SusEligibilityAdapter()
                else:
                    resolved_provider = PrivateInsuranceGatewayAdapter()

            service = ElegibilidadeService(
                provider=resolved_provider,
                notifier=notifier,
            )
            req = RequisicaoElegibilidade(
                organizacao_id=organizacao_id,
                atendimento_id=atend_uuid,
                paciente_id=paciente_uuid,
                cpf=cpf,
                cns=cns,
                operadora_id=operadora_id,
                numero_carteirinha=numero_carteirinha,
            )

            # 3. Evaluate eligibility
            resultado = await service.avaliar_elegibilidade(req)

            if resultado.aprovado:
                valkey = get_valkey_from_ctx(ctx)
                fila_service = build_fila_service_for_session(
                    valkey=valkey, session=session
                )
                try:
                    adm_result = await fila_service.admitir_atendimento_apto(
                        organizacao_id=organizacao_id,
                        atendimento_id=atend_uuid,
                    )
                    if adm_result.promovido:
                        return {
                            "status": "aprovado",
                            "aprovado": True,
                            "codigo_autorizacao": resultado.codigo_autorizacao,
                            "score": adm_result.score,
                        }
                    return {
                        "status": "already_promoted",
                        "aprovado": True,
                        "current_status": adm_result.status,
                    }
                except NotFoundError:
                    logger.warning(
                        "Attendance %s not found in DB during eligibility promotion",
                        atendimento_id,
                    )
                    return {"status": "not_found", "aprovado": True}

            # Failure / Timeout
            logger.warning(
                "Eligibility check failed for attendance %s: status=%s motivo=%s",
                atendimento_id,
                resultado.status.value,
                resultado.motivo,
            )
            return {
                "status": resultado.status.value,
                "aprovado": False,
                "motivo": resultado.motivo,
            }
