"""Asynchronous health insurance and SUS eligibility verification task (RF-02, RN03)."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from src.core.context import tenant_context
from src.modules.billing import (
    ElegibilidadeNotifierPort,
    ElegibilidadeService,
    EligibilityProviderPort,
    PrivateInsuranceGatewayAdapter,
    RequisicaoElegibilidade,
    SusEligibilityAdapter,
)
from src.modules.queue.application.services.fila_service import calcular_score_fila
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
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
       - Transitions attendance from TRIADO_AGUARDANDO_ELEGIBILIDADE to
         APTO_PARA_CHAMADA in PostgreSQL.
       - Injects attendance into Valkey ZSET (fila:{org}:aptos) with 64-bit score.
    4. On rejection / timeout:
       - Preserves attendance status in TRIADO_AGUARDANDO_ELEGIBILIDADE (RF-05).
       - Dispatches alert notification to patient waiting room for regularisation.
    """
    atend_uuid = UUID(atendimento_id)
    paciente_uuid = UUID(paciente_id)

    with tenant_context(organizacao_id):
        async with get_db_session_from_ctx(ctx) as session:
            # 1. Discover mode if not provided
            is_sus = modo_publico_sus
            if is_sus is None:
                stmt = text(
                    "SELECT modo_publico_sus FROM organizacoes WHERE id = :org_id"
                )
                res = await session.execute(stmt, {"org_id": organizacao_id})
                row = res.fetchone()
                is_sus = bool(row[0]) if row is not None else False

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
                atendimento = await session.get(Atendimento, atend_uuid)
                if not atendimento:
                    logger.warning(
                        "Attendance %s not found in DB during eligibility promotion",
                        atendimento_id,
                    )
                    return {"status": "not_found", "aprovado": True}

                if (
                    atendimento.status
                    == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
                ):
                    atendimento.promover_para_apto()
                    await session.commit()

                    # Ingest into Valkey ZSET
                    valkey = get_valkey_from_ctx(ctx)
                    ts_base = atendimento.data_entrada_fila or atendimento.criado_em
                    score = calcular_score_fila(atendimento.prioridade_clinica, ts_base)
                    k_fila = f"fila:{organizacao_id}:aptos"
                    await valkey.zadd(  # pyright: ignore[reportUnknownMemberType]
                        k_fila, {atendimento_id: score}
                    )

                    logger.info(
                        "Attendance %s approved and ingested into queue %s (score=%d)",
                        atendimento_id,
                        k_fila,
                        score,
                    )
                    return {
                        "status": "aprovado",
                        "aprovado": True,
                        "codigo_autorizacao": resultado.codigo_autorizacao,
                        "score": score,
                    }

                logger.info(
                    "Attendance %s already in state %s; skipped promotion",
                    atendimento_id,
                    atendimento.status,
                )
                return {
                    "status": "already_promoted",
                    "aprovado": True,
                    "current_status": atendimento.status,
                }

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
