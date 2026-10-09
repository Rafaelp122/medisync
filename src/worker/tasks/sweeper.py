"""Periodic self-healing sweeper reconciling PostgreSQL queue with Valkey (RN03)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.context import tenant_context
from src.modules.identity.composition import get_identity_reader
from src.modules.queue.composition import build_fila_service_for_session
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.sweeper")


@monitored_task
async def reconciliar_fila_orphans_task(
    ctx: dict[str, Any],
    organizacao_id: int | None = None,
    threshold_segundos: int = 60,
) -> dict[str, Any]:
    """Sweeps PostgreSQL for APTO_PARA_CHAMADA attendances missing from Valkey.

    Delegates reconciliation logic to FilaService to maintain single locality
    over queue storage and Valkey key namespaces.
    """
    valkey = get_valkey_from_ctx(ctx)
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_segundos)

    target_org_ids: list[int] = []
    if organizacao_id is not None:
        target_org_ids = [organizacao_id]
    else:
        async with get_db_session_from_ctx(ctx) as session:
            identity_reader = get_identity_reader(session)
            target_org_ids = await identity_reader.listar_organizacoes_ativas()

    total_scanned = 0
    total_reconciled = 0
    reconciled_ids: list[str] = []

    for org_id in target_org_ids:
        with tenant_context(org_id):
            async with get_db_session_from_ctx(ctx) as session:
                fila_service = build_fila_service_for_session(
                    valkey=valkey, session=session
                )
                scanned, reconciled = await fila_service.reconciliar_fila_orfaos(
                    organizacao_id=org_id,
                    cutoff_em=cutoff,
                )
                total_scanned += scanned
                total_reconciled += len(reconciled)
                reconciled_ids.extend(reconciled)

    logger.info(
        "Sweeper queue reconciliation finished: orgs=%d scanned=%d reconciled=%d",
        len(target_org_ids),
        total_scanned,
        total_reconciled,
    )

    return {
        "status": "success",
        "scanned_organizations": len(target_org_ids),
        "scanned_appointments": total_scanned,
        "reconciled_appointments": total_reconciled,
        "reconciled_ids": reconciled_ids,
    }
