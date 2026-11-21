"""Periodic self-healing sweeper reconciling PostgreSQL queue with Valkey (RN03)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.modules.queue.composition import build_fila_service_for_session
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.sweeper")


@monitored_task
async def reconciliar_fila_orphans_task(
    ctx: dict[str, Any],
    threshold_segundos: int = 60,
) -> dict[str, Any]:
    """Sweeps PostgreSQL for APTO_PARA_CHAMADA attendances missing from Valkey.

    Delegates reconciliation logic to FilaService to maintain single locality
    over queue storage and Valkey key namespaces.
    """
    valkey = get_valkey_from_ctx(ctx)
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_segundos)

    async with get_db_session_from_ctx(ctx) as session:
        fila_service = build_fila_service_for_session(valkey=valkey, session=session)
        total_scanned, reconciled_ids = await fila_service.reconciliar_fila_orfaos(
            cutoff_em=cutoff,
        )

    total_reconciled = len(reconciled_ids)
    logger.info(
        "Sweeper queue reconciliation finished: scanned=%d reconciled=%d",
        total_scanned,
        total_reconciled,
    )

    return {
        "status": "success",
        "scanned_appointments": total_scanned,
        "reconciled_appointments": total_reconciled,
        "reconciled_ids": reconciled_ids,
    }
